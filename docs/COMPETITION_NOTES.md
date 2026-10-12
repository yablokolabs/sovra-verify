# Verified source notes

[Official Track 2B template](https://github.com/HackApertus/project-template/blob/main/track_2b/README.md), checked October 12, 2026: new Apertus project; preserve `track_2b/`; public repository; Docker with root `make run`; technical report PDF max six pages excluding references; demo max two minutes; data directory max 100 MB. Submission is via the official hackathon portal, not Devpost. Target deployment must be on-premise, air-gapped, or sovereign Swiss cloud. Check official terms and input/output definitions before build. Judging covers AI use, rigour, value/cost/scalability, sovereignty and feasibility.

Prior-chat deadline: October 16, 2026 at 12:00 CEST / 15:30 IST. Not established by the template page; reconfirm official schedule before relying on it.

[CSCS API documentation](https://docs.cscs.ch/services/inference/api/#llm-inference-api-service), checked October 12: base `https://api.inference.cscs.ch/v1`, bearer auth, `/v1/models` and OpenAI-compatible `/v1/chat/completions` (plus Anthropic-compatible `/v1/messages` and `/v1/embeddings`). The docs' own examples use the variable name `CSCS_INFERENCE_API_KEY`. Accessible models depend on the key; docs list Apertus 1.5 8B/70B at a 262,144-token maximum context, and the `-thinking` variants are served with tool use disabled. Docs state CSCS does not record prompts or responses and data stays within infrastructure CSCS controls, and recommend auditing results. That covers inference traffic only, not application storage or hosting.

User-reported facts: project unstarted; CSCS key and HUGGING_FACE_API_KEY are in ~/.hermes/.env; $10 HF credit. Not independently verified. No secret values were read for this package.
