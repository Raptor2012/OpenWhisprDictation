# OpenWhispr Dictation

A local-only Windows dictation app derived from [OpenWhispr](https://github.com/OpenWhispr/openwhispr), with **Maeve**, a voice orb that reads your coding agent's replies aloud. Hold a key, speak, and clean text appears at your cursor. Speech recognition, cleanup and voice all run on your own computer: no cloud, no telemetry.

<p align="center">
  <a href="docs/media/openwhispr-dictation-demo.mp4"><img src="docs/media/demo-preview.webp" alt="OpenWhispr Dictation demo preview" width="860" /></a><br/>
  <sub>Silent preview. Click it for the full demo (1:28), narrated by Maeve.</sub>
</p>

## How it works

| Step | What runs | Where |
| --- | --- | --- |
| Hold the hotkey and speak | Parakeet unified 0.6B (int8) through sherpa-onnx, with a live preview | CPU, 8 threads |
| Release | Gemma 4 E4B cleanup through llama.cpp; short, simple lines use instant rule-based cleanup instead | GPU (Vulkan) |
| Paste | Text goes only into a verified writable field, otherwise to the clipboard | — |
| Maeve (optional) | Sends the dictation to a T3 Code thread and reads the reply with Phonon 31M TTS | CPU |

What changed versus upstream OpenWhispr is listed in [docs/windows-dictation-README.md](docs/windows-dictation-README.md). Maeve lives in [examples/t3-voice](examples/t3-voice/README.md). To start Maeve whenever the app opens, set `OPENWHISPR_COMPANION_COMMAND` to her launcher (`Start Maeve T3 Voice.cmd`).

## Benchmarks

Measured on 402 of the author's own dictations. Cleanup was scored against 137 hand-cleaned lines.

| Measure | Before | After |
| --- | --- | --- |
| Cleanup score vs. hand-cleaned text | 85.5 | 92.6 |
| Dictation → Maeve hand-off | 0.35–1.1 s | ~30 ms |
| Maeve's first audio | — | 55–90 ms |
| Key release → finished text | — | 1.6–2.6 s |

**Test machine:** Acer Predator Helios Neo 16 (PHN16-72) laptop, Intel Core i9-14900HX (24 cores, 32 threads), NVIDIA GeForce RTX 4070 Laptop GPU (8 GB), 32 GB RAM, Windows 11. Speech recognition ran on the CPU with 8 threads, cleanup on the GPU through Vulkan, and Maeve's voice on the CPU. Expect slower times on lighter hardware, especially without a GPU for cleanup. The cleanup list was tuned on the same dictations it is scored on, so treat 92.6 as optimistic.

## Build (Windows)

Use Node 24, then:

```powershell
npm ci
npm run build:renderer
npx electron-builder --win --dir --config electron-builder.unsigned-win.json --publish never
```

The unpacked app lands in `dist/win-unpacked/`. Native helpers and model runtimes are downloaded by the `scripts/download-*` scripts; see [docs/windows-dictation-README.md](docs/windows-dictation-README.md) for launch, rollback and known limitations.

## License and credits

MIT, like upstream (see [LICENSE](LICENSE)). Built on [OpenWhispr](https://github.com/OpenWhispr/openwhispr) by the OpenWhispr team; speech by [NVIDIA Parakeet](https://huggingface.co/nvidia) via [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx), cleanup by Google's Gemma through [llama.cpp](https://github.com/ggml-org/llama.cpp), and Maeve's voice by Gradium's Phonon. This project is not affiliated with or endorsed by OpenWhispr.

The original OpenWhispr README follows.

---

<p align="center">
  <img src="src/assets/logo.svg" alt="OpenWhispr" width="120" />
</p>

<h1 align="center">OpenWhispr</h1>

<p align="center">
  <a href="https://github.com/OpenWhispr/openwhispr/blob/main/LICENSE"><img src="https://img.shields.io/github/license/OpenWhispr/openwhispr?style=flat" alt="License" /></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey?style=flat" alt="Platform" />
  <a href="https://github.com/OpenWhispr/openwhispr/releases/latest"><img src="https://img.shields.io/github/v/release/OpenWhispr/openwhispr?style=flat&sort=semver" alt="GitHub release" /></a>
  <a href="https://github.com/OpenWhispr/openwhispr/releases"><img src="https://img.shields.io/github/downloads/OpenWhispr/openwhispr/total?style=flat&color=blue" alt="Downloads" /></a>
  <a href="https://github.com/OpenWhispr/openwhispr/stargazers"><img src="https://img.shields.io/github/stars/OpenWhispr/openwhispr?style=flat" alt="GitHub stars" /></a>
</p>

<p align="center">
  The open-source and free alternative to WisprFlow and Granola.<br/>
  Privacy-first voice-to-text dictation with AI agents, meeting transcription, and notes. Cross-platform for macOS, Windows, and Linux.
</p>

<p align="center">
  <a href="https://openwhispr.com">Website</a> &middot;
  <a href="https://docs.openwhispr.com">Docs</a> &middot;
  <a href="https://github.com/OpenWhispr/openwhispr/releases/latest">Download</a> &middot;
  <a href="https://docs.openwhispr.com/api/overview">API</a> &middot;
  <a href="https://github.com/OpenWhispr/openwhispr/blob/main/CHANGELOG.md">Changelog</a>
</p>

---

OpenWhispr turns your voice into text, notes, and actions from your desktop. Press a hotkey, speak, and your words appear at your cursor. Choose between fully private offline transcription with local speech-to-text models like Orukeet, Whisper, NVIDIA Parakeet, and Cohere Transcribe — where your audio never leaves your device — or cloud processing for speed. No data collection, no telemetry, fully open source.

## Download

| Platform              | Download                                                                                                                                                                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| macOS (Apple Silicon) | [`.dmg`](https://github.com/OpenWhispr/openwhispr/releases/latest)                                                                                                                                                                                                                        |
| macOS (Intel) \*      | [`.dmg`](https://github.com/OpenWhispr/openwhispr/releases/latest)                                                                                                                                                                                                                        |
| Windows               | [`.exe`](https://github.com/OpenWhispr/openwhispr/releases/latest)                                                                                                                                                                                                                        |
| Linux                 | [`.AppImage`](https://github.com/OpenWhispr/openwhispr/releases/latest) / [`.deb`](https://github.com/OpenWhispr/openwhispr/releases/latest) / [`.rpm`](https://github.com/OpenWhispr/openwhispr/releases/latest) / [`.tar.gz`](https://github.com/OpenWhispr/openwhispr/releases/latest) |

\* On Intel Macs, live speaker identification and voice fingerprinting are unavailable: they depend on ONNX Runtime, which [stopped shipping macOS x86_64 binaries in 1.24](https://github.com/microsoft/onnxruntime/releases/tag/v1.24.1). Meetings still record and transcribe normally, and notes search falls back to keyword matching instead of semantic search.

On macOS or x86_64 Linux, you can also install the community-maintained [Homebrew cask](https://formulae.brew.sh/cask/openwhispr):

```bash
brew install --cask openwhispr
```

## Features

- **Voice dictation** — global hotkey to dictate into any app with automatic pasting
- **Dictation translation** — dedicated hotkey to dictate in one language and paste the text in another
- **AI agent** — talk to GPT-5, Claude, Gemini, Groq, Tinfoil, OpenRouter, or local models with a named voice assistant
- **Voice Assistant hotkey** — dedicated hotkey that sends what you say straight to your AI assistant as a command, no wake word needed and no cleanup pass; highlighted text is edited in place. With auto-paste enabled, answers paste at a focused text cursor or stream into a floating panel and copy to the clipboard when no writable cursor is available. You can also opt in to sending a screenshot of your current screen as context
- **Meeting transcription** — auto-detect Zoom, Teams, and FaceTime calls with live speaker diarization, voice fingerprinting, and Google, Microsoft, or Apple Calendar integration
- **Local speaker diarization** — on-device speaker labelling with voice fingerprint recognition across meetings, no cloud required
- **Notes** — create, organize, and search notes with folders, semantic search, cloud sync, and AI actions
- **Team spaces & sharing** — free for signed-in users; share notes on the web with link, domain, or invite-only visibility, and collaborate in team spaces with roles, invitations, and server-enforced membership
- **Audio import** — transcribe existing audio and video: drag in files, batch-upload, or paste a YouTube/audio URL, with optional speaker detection
- **Local or cloud — your choice** — all core features (transcription, AI reasoning, speaker diarization, semantic search) work with local models or cloud providers — including GPU-accelerated local Whisper on Metal, CUDA, and Vulkan (AMD/Intel)
- **Enterprise controls** — enforce organization policy, company SSO and SCIM, and centrally managed Amazon Bedrock or Azure OpenAI access without distributing cloud keys
- **Public API & MCP** — manage notes and transcriptions programmatically or connect your AI assistant via the [MCP server](https://docs.openwhispr.com/integrations/mcp)

## Quick start

```bash
git clone https://github.com/OpenWhispr/openwhispr.git
cd openwhispr
npm install
npm run dev
```

Requires Node.js 24+. See the [full documentation](https://docs.openwhispr.com/quickstart) for setup guides, platform-specific instructions, and build details.

The commands above run the desktop application, which remains at the repository root. The Expo mobile application lives in [`openwhispr-mobile`](openwhispr-mobile/) with its own dependencies, lockfile, build configuration, and release process. See the [mobile README](openwhispr-mobile/README.md) for its setup instructions.

## Documentation

Visit **[docs.openwhispr.com](https://docs.openwhispr.com)** for:

- [Getting started](https://docs.openwhispr.com/quickstart)
- [Platform guides](https://docs.openwhispr.com/platform/macos) (macOS, Windows, Linux)
- [API reference](https://docs.openwhispr.com/api/overview)
- [MCP server setup](https://docs.openwhispr.com/integrations/mcp)
- [Troubleshooting](https://docs.openwhispr.com/troubleshooting)

Repo examples:

- [Custom ASR shim](examples/custom-asr-shim/) for Self-Hosted transcription against non-OpenAI-compatible ASR APIs

## Tech stack

React 19, TypeScript, Tailwind CSS v4, Electron 41, better-sqlite3, whisper.cpp, sherpa-onnx, shadcn/ui

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=OpenWhispr/openwhispr&type=date&legend=top-left)](https://www.star-history.com/#OpenWhispr/openwhispr&type=date&legend=top-left)

## Sponsors

<p align="center">
  <a href="https://console.neon.tech/app/?promo=openwhispr">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://neon.com/brand/neon-logo-dark-color.svg">
      <source media="(prefers-color-scheme: light)" srcset="https://neon.com/brand/neon-logo-light-color.svg">
      <img width="250" alt="Neon" src="https://neon.com/brand/neon-logo-light-color.svg">
    </picture>
  </a>
</p>

<p align="center"><a href="https://console.neon.tech/app/?promo=openwhispr">Neon</a> is the serverless Postgres platform powering OpenWhispr Cloud.</p>

## Contributing

We welcome contributions. Fork the repo, create a feature branch, and open a pull request. See the [contributing guide](https://docs.openwhispr.com/contributing) for development setup and guidelines.

## License

[MIT](LICENSE) — free for personal and commercial use.

## Acknowledgments

- **[OpenAI Whisper](https://github.com/openai/whisper)** — speech recognition model powering local and cloud transcription
- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — high-performance C++ implementation for local processing
- **[NVIDIA Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)** — fast multilingual ASR model
- **[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)** — cross-platform ONNX runtime for Parakeet inference
- **[Hugging Face](https://huggingface.co/)** — model hub hosting Whisper, Parakeet, and embedding model weights
- **[llama.cpp](https://github.com/ggerganov/llama.cpp)** — local LLM inference for AI text processing
- **[Electron](https://www.electronjs.org/)** — cross-platform desktop framework
- **[React](https://react.dev/)** — UI component library
- **[shadcn/ui](https://ui.shadcn.com/)** — accessible components built on Radix primitives
- **[Neon](https://console.neon.tech/app/?promo=openwhispr)** — serverless Postgres powering OpenWhispr Cloud
