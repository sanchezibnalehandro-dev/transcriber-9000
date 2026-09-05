// Adapted from Meetily v0.4.0 llama-helper:
// https://github.com/Zackriya-Solutions/meetily/tree/v0.4.0/llama-helper
// Meetily is Copyright (c) 2024 Zackriya Solutions and licensed under MIT.
// Transcriber 9000 changes: explicit GPU layers, Python-owned lifecycle, and
// a deliberately small JSON Lines protocol. See ../../THIRD_PARTY_NOTICES.md.

use std::io::{self, BufRead, Write};
use std::num::NonZeroU32;
use std::path::{Path, PathBuf};
use std::pin::pin;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use anyhow::{bail, Context, Result};
use llama_cpp_2::context::params::LlamaContextParams;
use llama_cpp_2::llama_backend::LlamaBackend;
use llama_cpp_2::llama_batch::LlamaBatch;
use llama_cpp_2::model::params::LlamaModelParams;
use llama_cpp_2::model::{AddBos, LlamaModel};
use serde::{Deserialize, Serialize};

const DEFAULT_CONTEXT_SIZE: u32 = 16_384;
const DEFAULT_MAX_TOKENS: i32 = 2_200;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Request {
    Generate {
        prompt: String,
        model_path: String,
        #[serde(default = "default_context_size")]
        context_size: u32,
        #[serde(default)]
        gpu_layers: u32,
        #[serde(default = "default_max_tokens")]
        max_tokens: i32,
        temperature: Option<f32>,
        top_k: Option<i32>,
        top_p: Option<f32>,
        presence_penalty: Option<f32>,
        frequency_penalty: Option<f32>,
        repeat_penalty: Option<f32>,
        penalty_last_n: Option<i32>,
        #[serde(default)]
        stop_tokens: Vec<String>,
    },
    Ping,
    Shutdown,
}

#[derive(Debug, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum Response {
    Response { text: String, error: Option<String> },
    Pong,
    Goodbye,
    Error { message: String },
}

fn default_context_size() -> u32 {
    DEFAULT_CONTEXT_SIZE
}

fn default_max_tokens() -> i32 {
    DEFAULT_MAX_TOKENS
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct SamplingConfig {
    temperature: f32,
    top_k: i32,
    top_p: f32,
    presence_penalty: f32,
    frequency_penalty: f32,
    repeat_penalty: f32,
    penalty_last_n: i32,
}

impl SamplingConfig {
    #[allow(clippy::too_many_arguments)]
    fn from_request(
        temperature: Option<f32>,
        top_k: Option<i32>,
        top_p: Option<f32>,
        presence_penalty: Option<f32>,
        frequency_penalty: Option<f32>,
        repeat_penalty: Option<f32>,
        penalty_last_n: Option<i32>,
    ) -> Self {
        let temperature = finite_or(temperature, 0.2).max(0.0);
        let top_k = top_k.unwrap_or(64).max(1);
        let top_p = finite_or(top_p, 0.9);
        let top_p = if top_p > 0.0 && top_p <= 1.0 {
            top_p
        } else {
            1.0
        };
        let presence_penalty = finite_or(presence_penalty, 0.0).max(0.0);
        let frequency_penalty = finite_or(frequency_penalty, 0.0).max(0.0);
        let repeat_penalty = finite_or(repeat_penalty, 1.0);
        let repeat_penalty = if repeat_penalty > 0.0 {
            repeat_penalty
        } else {
            1.0
        };
        let penalty_last_n = penalty_last_n.unwrap_or(0).max(0);

        Self {
            temperature,
            top_k,
            top_p,
            presence_penalty,
            frequency_penalty,
            repeat_penalty,
            penalty_last_n,
        }
    }

    fn uses_penalties(&self) -> bool {
        self.penalty_last_n > 0
            && (self.presence_penalty > 0.0
                || self.frequency_penalty > 0.0
                || (self.repeat_penalty - 1.0).abs() > f32::EPSILON)
    }
}

fn finite_or(value: Option<f32>, fallback: f32) -> f32 {
    match value {
        Some(value) if value.is_finite() => value,
        _ => fallback,
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ModelKey {
    path: PathBuf,
    context_size: u32,
    gpu_layers: u32,
}

struct ModelState {
    backend: LlamaBackend,
    model: Option<LlamaModel>,
    key: Option<ModelKey>,
}

impl ModelState {
    fn new() -> Result<Self> {
        let backend = LlamaBackend::init().context("failed to initialize llama backend")?;
        Ok(Self {
            backend,
            model: None,
            key: None,
        })
    }

    fn load_model_if_needed(
        &mut self,
        model_path: &Path,
        context_size: u32,
        gpu_layers: u32,
    ) -> Result<()> {
        if context_size == 0 {
            bail!("context_size must be greater than zero");
        }

        let path = model_path
            .canonicalize()
            .with_context(|| format!("model file does not exist: {}", model_path.display()))?;
        if !path.is_file() {
            bail!("model path is not a file: {}", path.display());
        }

        let key = ModelKey {
            path: path.clone(),
            context_size,
            gpu_layers,
        };

        if self.key.as_ref() == Some(&key) && self.model.is_some() {
            eprintln!("Model already loaded");
            return Ok(());
        }

        let load_started = Instant::now();
        eprintln!(
            "Loading model: {} (context_size={}, gpu_layers={})",
            path.display(),
            context_size,
            gpu_layers
        );

        let model_params = LlamaModelParams::default().with_n_gpu_layers(gpu_layers);
        let model_params = pin!(model_params);
        let model = LlamaModel::load_from_file(&self.backend, path, &model_params)
            .context("failed to load model")?;

        self.model = Some(model);
        self.key = Some(key);
        eprintln!("Model loaded successfully");
        eprintln!(
            "METRIC model_load_seconds={:.6}",
            load_started.elapsed().as_secs_f64()
        );
        Ok(())
    }

    fn generate(
        &self,
        prompt: &str,
        max_tokens: i32,
        sampling: SamplingConfig,
        stop_tokens: &[String],
    ) -> Result<String> {
        if prompt.trim().is_empty() {
            bail!("prompt must not be empty");
        }
        if max_tokens <= 0 {
            bail!("max_tokens must be greater than zero");
        }

        let key = self.key.as_ref().context("model is not loaded")?;
        let model = self.model.as_ref().context("model is not loaded")?;
        let started = Instant::now();

        let threads = std::thread::available_parallelism()
            .map(|count| ((count.get() as i32 / 2) + 2).max(1))
            .unwrap_or(2);
        let context_size = NonZeroU32::new(key.context_size).context("invalid context size")?;
        let context_params = LlamaContextParams::default()
            .with_n_ctx(Some(context_size))
            .with_n_batch(key.context_size)
            .with_n_threads(threads)
            .with_n_threads_batch(threads);
        let mut context = model
            .new_context(&self.backend, context_params)
            .context("failed to create llama context")?;

        let prompt_tokens = model
            .str_to_token(prompt, AddBos::Always)
            .context("failed to tokenize prompt")?;
        if prompt_tokens.is_empty() {
            bail!("prompt produced no tokens");
        }

        let prompt_count = prompt_tokens.len();
        let requested_total = prompt_count
            .checked_add(max_tokens as usize)
            .context("token count overflow")?;
        if requested_total > key.context_size as usize {
            bail!(
                "prompt plus requested output exceeds context: prompt_tokens={}, max_tokens={}, context_size={}",
                prompt_count,
                max_tokens,
                key.context_size
            );
        }

        eprintln!(
            "Generation started: prompt_tokens={}, max_tokens={}, context_size={}",
            prompt_count, max_tokens, key.context_size
        );

        let mut batch = LlamaBatch::new(key.context_size as usize, 1);
        let last_prompt_index = (prompt_count - 1) as i32;
        for (position, token) in (0_i32..).zip(prompt_tokens.into_iter()) {
            batch
                .add(token, position, &[0], position == last_prompt_index)
                .context("failed to add prompt token to batch")?;
        }
        context
            .decode(&mut batch)
            .context("failed to decode prompt")?;
        let prompt_processing_seconds = started.elapsed().as_secs_f64();
        eprintln!(
            "METRIC prompt_processing_seconds={prompt_processing_seconds:.6}"
        );

        use llama_cpp_2::sampling::LlamaSampler;
        let seed = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u32;
        let sampler = if sampling.temperature <= 0.0 {
            if sampling.uses_penalties() {
                LlamaSampler::chain_simple([
                    LlamaSampler::penalties(
                        model.n_vocab(),
                        sampling.penalty_last_n,
                        sampling.repeat_penalty,
                        sampling.frequency_penalty,
                        sampling.presence_penalty,
                    ),
                    LlamaSampler::greedy(),
                ])
            } else {
                LlamaSampler::chain_simple([LlamaSampler::greedy()])
            }
        } else if sampling.uses_penalties() {
            LlamaSampler::chain_simple([
                LlamaSampler::penalties(
                    model.n_vocab(),
                    sampling.penalty_last_n,
                    sampling.repeat_penalty,
                    sampling.frequency_penalty,
                    sampling.presence_penalty,
                ),
                LlamaSampler::top_k(sampling.top_k),
                LlamaSampler::top_p(sampling.top_p, 1),
                LlamaSampler::temp(sampling.temperature),
                LlamaSampler::dist(seed),
            ])
        } else {
            LlamaSampler::chain_simple([
                LlamaSampler::top_k(sampling.top_k),
                LlamaSampler::top_p(sampling.top_p, 1),
                LlamaSampler::temp(sampling.temperature),
                LlamaSampler::dist(seed),
            ])
        };
        let mut sampler = pin!(sampler);

        let mut decoder = encoding_rs::UTF_8.new_decoder();
        let mut output = String::new();
        let mut current_position = prompt_count as i32;
        let mut generated_tokens = 0_i32;

        while generated_tokens < max_tokens {
            let token = sampler.as_mut().sample(&context, batch.n_tokens() - 1);
            sampler.as_mut().accept(token);

            if model.is_eog_token(token) {
                break;
            }

            let bytes = match model.token_to_piece_bytes(token, 32, true, None) {
                Err(llama_cpp_2::TokenToStringError::InsufficientBufferSpace(size)) => {
                    let required: usize = size
                        .checked_neg()
                        .context("invalid token buffer size")?
                        .try_into()
                        .context("invalid token buffer size")?;
                    model.token_to_piece_bytes(token, required, true, None)
                }
                result => result,
            }
            .context("failed to decode generated token")?;

            let mut piece = String::with_capacity(bytes.len());
            let _ = decoder.decode_to_string(&bytes, &mut piece, false);
            output.push_str(&piece);
            generated_tokens += 1;

            if let Some(stop_at) = first_stop_position(&output, stop_tokens) {
                output.truncate(stop_at);
                break;
            }

            batch.clear();
            batch
                .add(token, current_position, &[0], true)
                .context("failed to add generated token to batch")?;
            current_position += 1;
            context
                .decode(&mut batch)
                .context("failed to decode generated token")?;
        }

        let mut tail = String::new();
        let _ = decoder.decode_to_string(b"", &mut tail, true);
        output.push_str(&tail);
        let output = output.trim().to_owned();

        let total_seconds = started.elapsed().as_secs_f64();
        let generation_seconds = (total_seconds - prompt_processing_seconds).max(0.0);
        eprintln!(
            "Generation finished: output_tokens={}, elapsed_seconds={total_seconds:.2}",
            generated_tokens
        );
        eprintln!("METRIC generation_seconds={generation_seconds:.6}");
        eprintln!("METRIC generation_total_seconds={total_seconds:.6}");
        Ok(output)
    }
}

fn first_stop_position(output: &str, stop_tokens: &[String]) -> Option<usize> {
    stop_tokens
        .iter()
        .filter(|token| !token.is_empty())
        .filter_map(|token| output.find(token))
        .min()
}

fn send_response(response: &Response) -> Result<()> {
    let json = serde_json::to_string(response).context("failed to serialize response")?;
    let mut stdout = io::stdout().lock();
    stdout
        .write_all(json.as_bytes())
        .context("failed to write response")?;
    stdout.write_all(b"\n").context("failed to write newline")?;
    stdout.flush().context("failed to flush response")?;
    Ok(())
}

fn handle_generate(state: &mut ModelState, request: Request) -> Response {
    let Request::Generate {
        prompt,
        model_path,
        context_size,
        gpu_layers,
        max_tokens,
        temperature,
        top_k,
        top_p,
        presence_penalty,
        frequency_penalty,
        repeat_penalty,
        penalty_last_n,
        stop_tokens,
    } = request
    else {
        unreachable!("handle_generate called with non-generate request");
    };

    if let Err(error) = state.load_model_if_needed(
        Path::new(&model_path),
        context_size,
        gpu_layers,
    ) {
        return Response::Response {
            text: String::new(),
            error: Some(format!("model load failed: {error:#}")),
        };
    }

    let sampling = SamplingConfig::from_request(
        temperature,
        top_k,
        top_p,
        presence_penalty,
        frequency_penalty,
        repeat_penalty,
        penalty_last_n,
    );

    match state.generate(&prompt, max_tokens, sampling, &stop_tokens) {
        Ok(text) => Response::Response { text, error: None },
        Err(error) => Response::Response {
            text: String::new(),
            error: Some(format!("generation failed: {error:#}")),
        },
    }
}

fn main() -> Result<()> {
    eprintln!("llama-helper starting");
    let mut state = ModelState::new()?;
    let stdin = io::stdin();

    for line in stdin.lock().lines() {
        let line = match line {
            Ok(line) => line,
            Err(error) => {
                eprintln!("stdin read failed: {error}");
                break;
            }
        };
        if line.trim().is_empty() {
            continue;
        }

        match serde_json::from_str::<Request>(&line) {
            Ok(request @ Request::Generate { .. }) => {
                send_response(&handle_generate(&mut state, request))?;
            }
            Ok(Request::Ping) => send_response(&Response::Pong)?,
            Ok(Request::Shutdown) => {
                send_response(&Response::Goodbye)?;
                break;
            }
            Err(error) => {
                eprintln!("invalid request: {error}");
                send_response(&Response::Error {
                    message: format!("invalid request: {error}"),
                })?;
            }
        }
    }

    eprintln!("llama-helper exiting");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn protocol_defaults_match_poc() {
        let request: Request = serde_json::from_str(
            r#"{"type":"generate","prompt":"тест","model_path":"model.gguf"}"#,
        )
        .unwrap();

        let Request::Generate {
            context_size,
            gpu_layers,
            max_tokens,
            ..
        } = request
        else {
            panic!("expected generate request");
        };

        assert_eq!(context_size, 16_384);
        assert_eq!(gpu_layers, 0);
        assert_eq!(max_tokens, 2_200);
    }

    #[test]
    fn response_is_one_json_line_even_with_multiline_text() {
        let response = Response::Response {
            text: "первая строка\nвторая строка".to_owned(),
            error: None,
        };
        let serialized = serde_json::to_string(&response).unwrap();
        assert!(!serialized.contains('\n'));
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(&serialized).unwrap()["type"],
            "response"
        );
    }

    #[test]
    fn stop_tokens_use_earliest_match() {
        let stops = vec!["END".to_owned(), "STOP".to_owned()];
        assert_eq!(first_stop_position("текст STOP потом END", &stops), Some(11));
    }
}
