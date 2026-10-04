# Third-party notices

## OpenCode

O.R.S.I.'s model-first capability routing, bounded structured-call repair, invalid-call feedback,
and continuation behavior are substantially derived from architectural and behavioral patterns in
OpenCode.

- Upstream repository: <https://github.com/anomalyco/opencode>
- Revision used: `d870e22c70f27103016dcd479edcfebf86136d93`
- Cloud Phase 1 reference: `907b3bc518fa48e90e8ec24dd327d13eee71c36c`.
  Responses selection (`provider/provider.ts`), capability-gated sampling
  (`session/llm/request.ts`), and disabled response storage (`provider/transform.ts`)
  are adapted in the Python OpenAI backend. OpenAI documentation governs API behavior.
- Cloud Phase 2.1 uses that same revision's Responses protocol, input converter and
  tool preparation patterns. `app/inference/openai_tools.py` adapts flat function
  definitions and exact call/result ID pairing. It explicitly uses strict schemas
  per OpenAI documentation; the upstream protocol's non-strict default is not ported.
- Upstream files used as references:
  - `packages/opencode/src/session/tools.ts`
  - `packages/opencode/src/session/llm.ts`
  - `packages/opencode/src/session/llm/request.ts`
  - `packages/opencode/src/session/llm/native-request.ts`
  - `packages/opencode/src/session/llm/native-runtime.ts`
  - `packages/opencode/src/session/processor.ts`
  - `packages/opencode/src/session/prompt.ts`
  - `packages/opencode/src/tool/registry.ts`
  - `packages/opencode/src/tool/tool.ts`
  - `packages/opencode/src/tool/json-schema.ts`
  - `packages/opencode/src/tool/invalid.ts`
  - `packages/opencode/src/provider/transform.ts`
  - `packages/opencode/src/permission/index.ts`

O.R.S.I. files containing substantially derived behavior are:

- `app/agent/runtime.py`
- `app/agent/feedback.py`
- `app/inference/tool_repair.py`
- `app/inference/openai_backend.py` (cloud Phase 1 reference)
- `app/inference/openai_tools.py` (cloud Phase 2.1 reference)

The implementation is a Python/Pydantic adaptation for O.R.S.I.; no block of upstream TypeScript
was copied verbatim.

OpenCode license at the pinned revision:

```text
MIT License

Copyright (c) 2025 opencode

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
