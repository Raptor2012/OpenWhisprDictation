# Full upstream suite failure inventory - 2026-10-28

Source log: `fulltest-after-triage.log`; exit 1. Three stalled cloud workers were deliberately stopped: `audioManagerCustomUpload`, `audioManagerStreamingFinalization`, and `audioManagerStreamingRouting`. This was a diagnostic run, not a clean full-suite pass.

```text
ℹ tests 9034
ℹ suites 8
ℹ pass 8384
ℹ fail 107
ℹ cancelled 0
ℹ skipped 542
ℹ todo 1
ℹ duration_ms 1376664.7201
```

The runner reports 107 failures. The inventory contains 100 individual failure entries and seven failed parent cases listed at the end; skip-marked diagnostic blocks are omitted. Two old raw-WAV fallback expectations were updated after their full-run worker loaded, and pass in the final 271-test supported gate. No `ReferenceError: module is not defined` remains.

## test/components/directionalContentPolicy.test.js

Removed UI: the old enterprise version notice no longer exists in the dedicated control panel.

- **localized sentences isolate technical interpolations without changing word order** (`test/components/directionalContentPolicy.test.js:123:1`)

```text
AssertionError [ERR_ASSERTION]: src/components/ControlPanel.tsx lost a bidi-isolated technical interpolation
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\directionalContentPolicy.test.js:161:12)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
      at Test.postRun (node:internal/test_runner/test:1330:19)
      at Test.run (node:internal/test_runner/test:1258:12)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
```

## test/components/enterpriseAudioSettings.test.js

Changed local defaults conflict with upstream cloud/provider default or migration expectations.

- **meeting and upload mode picks leave the shared enterprise setup mode to its explicit controls** (`test/components/enterpriseAudioSettings.test.js:108:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'nvidia'
  - 'whisper'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\enterpriseAudioSettings.test.js:244:26)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/components/fieldDirectionPolicy.test.js

Stale UI inventory: new auto-direction transcript/alias fields and inherited checkbox directions are absent from the old reviewed manifest.

- **every shared Input and Textarea consumer has an explicit reviewed classification** (`test/components/fieldDirectionPolicy.test.js:156:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  ... Skipped lines
  
    {
      'src/components/ApiKeysSection.tsx': [
        'auto'
      ],
```

- **native text fields use the same reviewed direction policy** (`test/components/fieldDirectionPolicy.test.js:161:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    {
      'src/components/ApiKeysSection.tsx': [
        'inherit'
      ],
      'src/components/CommandSearch.tsx': [
```

## test/components/leaderboardNavigation.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **the leaderboard is tabbed inside the Insights view** (`test/components/leaderboardNavigation.test.js:8:1`)

```text
AssertionError [ERR_ASSERTION]: false == true
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\leaderboardNavigation.test.js:18:10)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.start (node:internal/test_runner/test:1096:17)
      at startSubtestAfterBootstrap (node:internal/test_runner/harness:385:17) {
    generatedMessage: true,
    code: 'ERR_ASSERTION',
```

## test/components/noteEditorSummaryDeletion.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **Keep leaves the banner up for a retry when the flush step fails** (`test/components/noteEditorSummaryDeletion.test.js:901:3`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  2 !== 1
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\noteEditorSummaryDeletion.test.js:917:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

## test/components/orukeetOrganization.test.js

Changed local defaults conflict with upstream cloud/provider default or migration expectations.

- **adding Orukeet preserves fresh-install transcription modes and existing backend defaults** (`test/components/orukeetOrganization.test.js:90:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  true !== false
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\orukeetOrganization.test.js:96:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

## test/components/pillCommandMenu.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **the command menu hides Ask Assistant while a recording is active** (`test/components/pillCommandMenu.test.js:34:1`)

```text
AssertionError [ERR_ASSERTION]: The input did not match the regular expression /askAssistant/. Input:
  
  '<div class="absolute bottom-full right-0 mb-3 w-48 overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg backdrop-blur-sm"><button class="w-full px-3 py-2 text-start text-sm font-medium hover:bg-muted focus:bg-muted focus:outline-none">app.commandMenu.startListening</button><div class="h-px bg-border"></div><button class="w-full px-3 py-2 text-start text-sm hover:bg-muted focus:bg-muted focus:outline-none">app.commandMenu.hideForNow</button></div>'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\pillCommandMenu.test.js:36:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/ha
```

- **the command menu offers a meeting recording only while idle and allowed** (`test/components/pillCommandMenu.test.js:67:1`)

```text
AssertionError [ERR_ASSERTION]: The input did not match the regular expression /startMeetingRecording/. Input:
  
  '<div class="absolute bottom-full right-0 mb-3 w-48 overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg backdrop-blur-sm"><button class="w-full px-3 py-2 text-start text-sm font-medium hover:bg-muted focus:bg-muted focus:outline-none">app.commandMenu.startListening</button><div class="h-px bg-border"></div><button class="w-full px-3 py-2 text-start text-sm hover:bg-muted focus:bg-muted focus:outline-none">app.commandMenu.hideForNow</button></div>'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\pillCommandMenu.test.js:68:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test
```

## test/components/uploadAudioPolicyFeedback.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **upload policy feedback names the disabled feature independently of recording and updates without a reload** (`test/components/uploadAudioPolicyFeedback.test.js:49:1`)

```text
TypeError: Cannot read properties of null (reading 'disabled')
      at uploadInputs (D:\Teacher\OpenWhisprDictation\test\components\uploadAudioPolicyFeedback.test.js:43:25)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\components\uploadAudioPolicyFeedback.test.js:108:24)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:385:3)
```

## test/helpers/accountScopeIpc.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **signed-out transitions restore guest meeting detection without granting a replacement bearer guest permissions** (`test/helpers/accountScopeIpc.test.js:275:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    {
  +   audioDetection: false,
  +   processDetection: false
  -   audioDetection: true,
  -   processDetection: true
```

## test/helpers/audioManagerCleanupFallback.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **cleanup failure details ride the raw result instead of notifying before paste** (`test/helpers/audioManagerCleanupFallback.test.js:5:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
  + {}
  - {
  -   cleanupFailure: {
  -     action: 'Run the command below in your terminal to re-authenticate:',
  -     actionKey: 'reasoning.enterprise.errors.bedrock.actions.reauthenticate',
```

- **a truncated cleanup inside the translation chain still reports the failure** (`test/helpers/audioManagerCleanupFallback.test.js:106:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'original dictation'
  - 'dictado traducido'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerCleanupFallback.test.js:180:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/audioManagerCleanupUnconfigured.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **cleanup on with no model warns once it is shown, and again after a fix breaks** (`test/helpers/audioManagerCleanupUnconfigured.test.js:55:1`)

```text
TypeError: Cannot read properties of undefined (reading 'messageKey')
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerCleanupUnconfigured.test.js:59:22)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:385:3)
```

- **cleanup with nothing to run on warns even when the assistant is reachable** (`test/helpers/audioManagerCleanupUnconfigured.test.js:83:1`)

```text
TypeError: Cannot read properties of undefined (reading 'messageKey')
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerCleanupUnconfigured.test.js:93:56)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7)
```

- **a BYOK cleanup model with no API key reports the missing key** (`test/helpers/audioManagerCleanupUnconfigured.test.js:96:1`)

```text
TypeError: Cannot read properties of undefined (reading 'messageKey')
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerCleanupUnconfigured.test.js:103:24)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7)
```

## test/helpers/audioManagerCustomUpload.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **test\helpers\audioManagerCustomUpload.test.js** (`test/helpers/audioManagerCustomUpload.test.js:1:1`)

```text
'test failed'
```

## test/helpers/audioManagerDictionaryPromptRecovery.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **a strict retry exception reaches the configured cloud fallback** (`test/helpers/audioManagerDictionaryPromptRecovery.test.js:512:11`)

```text
Error: Local Whisper failed: IPC unavailable
      at AudioManager.processWithLocalWhisper (D:\Teacher\OpenWhisprDictation\src\helpers\audioManager.js:2546:13)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerDictionaryPromptRecovery.test.js:532:20)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerDictionaryPromptRecovery.test.js:512:3)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:385:3)
```

## test/helpers/audioManagerFailedAgentRoute.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **a transcript that succeeded is not lost when the agent selection edit fails** (`test/helpers/audioManagerFailedAgentRoute.test.js:97:1`)

```text
AssertionError [ERR_ASSERTION]: the edit failure is reported
  + actual - expected
  
  + undefined
  - 'SELECTION_EDIT_CAPTURE_FAILED'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerFailedAgentRoute.test.js:100:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **an OpenWhispr Cloud transcript is kept under Cloud's client id when the edit fails** (`test/helpers/audioManagerFailedAgentRoute.test.js:110:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + undefined
  - 'SELECTION_EDIT_CAPTURE_FAILED'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerFailedAgentRoute.test.js:129:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **the kept transcript never serializes with the error** (`test/helpers/audioManagerFailedAgentRoute.test.js:140:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + undefined
  - 'Nova, this is a long note about the quarterly plan.'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerFailedAgentRoute.test.js:157:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **a dictation cancelled during the selection edit saves nothing** (`test/helpers/audioManagerFailedAgentRoute.test.js:163:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  1 !== 0
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerFailedAgentRoute.test.js:178:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

- **a failure before any transcript exists still saves empty text** (`test/helpers/audioManagerFailedAgentRoute.test.js:182:1`)

```text
AssertionError [ERR_ASSERTION]: the STT failure is what is reported
  + actual - expected
  
  + undefined
  - 'PROVIDER_UNAVAILABLE'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerFailedAgentRoute.test.js:188:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/audioManagerRawWav.test.js

Updated after this worker loaded; both no-upload cases pass in the final supported gate.

- **a failed Parakeet decode falls back to the cloud with the WebM, never the WAV** (`test/helpers/audioManagerRawWav.test.js:85:1`)

```text
Error: Parakeet failed: engine down
      at AudioManager.processWithLocalParakeet (D:\Teacher\OpenWhisprDictation\src\helpers\audioManager.js:2633:13)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerRawWav.test.js:88:18)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7)
```

- **a failed whisper decode falls back to the cloud with the WebM, never the WAV** (`test/helpers/audioManagerRawWav.test.js:96:1`)

```text
Error: Local Whisper failed: engine down
      at AudioManager.processWithLocalWhisper (D:\Teacher\OpenWhisprDictation\src\helpers\audioManager.js:2546:13)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerRawWav.test.js:99:18)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7)
```

## test/helpers/audioManagerStreamingFinalization.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **test\helpers\audioManagerStreamingFinalization.test.js** (`test/helpers/audioManagerStreamingFinalization.test.js:1:1`)

```text
'test failed'
```

## test/helpers/audioManagerStreamingRouting.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **managed batch config does not disable BYOK OpenAI realtime transcription** (`test/helpers/audioManagerStreamingRouting.test.js:27:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:32:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:385:3) {
    generatedMessage: true,
```

- **Gemini streaming needs a streaming model, plus a key (byok) or an account (managed)** (`test/helpers/audioManagerStreamingRouting.test.js:97:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:108:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

- **deepgram/assemblyai byok stream on the key alone, never on the batch path** (`test/helpers/audioManagerStreamingRouting.test.js:124:1`)

```text
AssertionError [ERR_ASSERTION]: deepgram
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:138:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
```

- **explicit Orukeet custom endpoint uses PCM streaming without cloud login** (`test/helpers/audioManagerStreamingRouting.test.js:161:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:171:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

- **managed Orukeet rollout overrides stale personal provider and model without a key** (`test/helpers/audioManagerStreamingRouting.test.js:183:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:191:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

- **managed Orukeet only streams languages the model covers** (`test/helpers/audioManagerStreamingRouting.test.js:216:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerStreamingRouting.test.js:221:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

## test/helpers/audioManagerToneStyle.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **local and BYOK cleanup get the tone through the reasoning config** (`test/helpers/audioManagerToneStyle.test.js:143:11`)

```text
TypeError: Cannot read properties of undefined (reading 'toneStyle')
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerToneStyle.test.js:153:33)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerToneStyle.test.js:143:3)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async startSubtestAfterBootstrap (node:internal/test_runner/harness:385:3)
```

## test/helpers/audioManagerWakeWordLanguage.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **generic auto-language routing infers Arabic before an English UI fallback** (`test/helpers/audioManagerWakeWordLanguage.test.js:290:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + undefined
  - 'لخّص هذه الملاحظة'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\audioManagerWakeWordLanguage.test.js:307:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/cosmicToplevel.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **returns the activated toplevel's app id from a version 1 bind** (`test/helpers/cosmicToplevel.test.js:91:1`)

```text
Error: listen EACCES: permission denied C:\Users\Sanket\AppData\Local\Temp\ow-cosmic-dvgZ0s\wayland-test
      at Server.setupListenHandle [as _listen2] (node:net:1986:21)
      at listenInCluster (node:net:2065:12)
      at Server.listen (node:net:2187:5)
      at D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:85:12
      at new Promise (<anonymous>)
      at startCompositor (D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:84:10)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:92:32)
```

- **returns null when the compositor has no COSMIC toplevel info** (`test/helpers/cosmicToplevel.test.js:104:1`)

```text
Error: listen EACCES: permission denied C:\Users\Sanket\AppData\Local\Temp\ow-cosmic-hbV5Ti\wayland-test
      at Server.setupListenHandle [as _listen2] (node:net:1986:21)
      at listenInCluster (node:net:2065:12)
      at Server.listen (node:net:2187:5)
      at D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:85:12
      at new Promise (<anonymous>)
      at startCompositor (D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:84:10)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\cosmicToplevel.test.js:105:32)
```

## test/helpers/enterpriseAudioCredentials.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **the production vault rejects Linux basic_text before provisioning or importing plaintext** (`test/helpers/enterpriseAudioCredentials.test.js:87:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    Comparison {
  +   message: 'Enterprise bootstrap must be owned by the signed-in user and readable only by that user'
  -   message: 'OS-protected enterprise credential storage is unavailable'
    }
```

- **protected MDM imports bind the signed-in account and configured slots and remove plaintext only after success** (`test/helpers/enterpriseAudioCredentials.test.js:211:1`)

```text
Error: Enterprise bootstrap must be owned by the signed-in user and readable only by that user
      at bootstrapError (D:\Teacher\OpenWhisprDictation\src\helpers\enterpriseAudioBootstrap.js:10:17)
      at notProtected (D:\Teacher\OpenWhisprDictation\src\helpers\enterpriseAudioBootstrap.js:12:3)
      at assertProtectedBootstrap (D:\Teacher\OpenWhisprDictation\src\helpers\enterpriseAudioBootstrap.js:53:13)
      at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
      at async importEnterpriseAudioBootstrap (D:\Teacher\OpenWhisprDictation\src\helpers\enterpriseAudioBootstrap.js:79:5)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\enterpriseAudioCredentials.test.js:240:19)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **a failed import that can't be restored deletes its claimed plaintext** (`test/helpers/enterpriseAudioCredentials.test.js:325:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    Comparison {
  +   message: 'Enterprise bootstrap must be owned by the signed-in user and readable only by that user'
  -   message: 'vault write failed'
    }
```

## test/helpers/extractArchive.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **extractArchive rejects on corrupt zip when both extraction methods fail** (`test/helpers/extractArchive.test.js:106:1`)

```text
AssertionError [ERR_ASSERTION]: Missing expected rejection.
      at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\extractArchive.test.js:122:5)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
    code: 'ERR_ASSERTION',
    actual: undefined,
```

## test/helpers/hyprlandConfigPersistence.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **keeps an existing require loader byte- and inode-identical** (`test/helpers/hyprlandConfigPersistence.test.js:51:3`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
    '-- user config\n' +
  +   'pcall(require, "C:\\\\Users\\\\Sanket\\\\AppData\\\\Local\\\\Temp\\\\hyprland-config-test-wjqBR5\\\\openwhispr-binds.lua")\n' +
  -   "require ( 'C:\\Users\\Sanket\\AppData\\Local\\Temp\\hyprland-config-test-wjqBR5\\openwhispr-binds.lua' )\n" +
      'return {}\n'
```

- **keeps an existing pcall dofile loader byte- and inode-identical** (`test/helpers/hyprlandConfigPersistence.test.js:51:3`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
    '-- user config\n' +
      "pcall ( dofile, 'C:\\Users\\Sanket\\AppData\\Local\\Temp\\hyprland-config-test-twMOEM\\openwhispr-binds.lua' )\n" +
  +   'pcall(require, "C:\\\\Users\\\\Sanket\\\\AppData\\\\Local\\\\Temp\\\\hyprland-config-test-twMOEM\\\\openwhispr-binds.lua")\n' +
      'return {}\n'
```

- **keeps an existing require without parentheses loader byte- and inode-identical** (`test/helpers/hyprlandConfigPersistence.test.js:51:3`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
    '-- user config\n' +
      "require 'C:\\Users\\Sanket\\AppData\\Local\\Temp\\hyprland-config-test-b48LJe\\openwhispr-binds.lua'\n" +
  +   'pcall(require, "C:\\\\Users\\\\Sanket\\\\AppData\\\\Local\\\\Temp\\\\hyprland-config-test-b48LJe\\\\openwhispr-binds.lua")\n' +
      'return {}\n'
```

- **keeps an existing multiline dofile loader byte- and inode-identical** (`test/helpers/hyprlandConfigPersistence.test.js:51:3`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
    '-- user config\n' +
      'dofile(\n' +
      "  'C:\\Users\\Sanket\\AppData\\Local\\Temp\\hyprland-config-test-4WPYG1\\openwhispr-binds.lua'\n" +
      ')\n' +
  +   'pcall(require, "C:\\\\Users\\\\Sanket\\\\AppData\\\\Local\\\\Temp\\\\hyprland-config-test-4WPYG1\\\\openwhispr-binds.lua")\n' +
```

- **replaces the main config atomically through a symlink, preserving its target mode** (`test/helpers/hyprlandConfigPersistence.test.js:63:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-S7CBs9\chezmoi-source.lua' -> 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-S7CBs9\hyprland.lua'
      at Object.symlinkSync (node:fs:1853:11)
      at D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:69:8
      at fixture (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:35:12)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:64:3)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
```

- **failed atomic replacement leaves the original target and symlink intact** (`test/helpers/hyprlandConfigPersistence.test.js:126:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-ISGRfh\source.lua' -> 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-ISGRfh\hyprland.lua'
      at Object.symlinkSync (node:fs:1853:11)
      at D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:130:8
      at fixture (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:35:12)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:127:3)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
```

- **does not replace a dangling config symlink** (`test/helpers/hyprlandConfigPersistence.test.js:145:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-CoqG8J\missing.lua' -> 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-CoqG8J\hyprland.lua'
      at Object.symlinkSync (node:fs:1853:11)
      at D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:147:8
      at fixture (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:35:12)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:146:3)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
```

- **repeating persistence leaves both an existing loader and unchanged managed binds untouched** (`test/helpers/hyprlandConfigPersistence.test.js:162:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-4ETbb4\managed.lua' -> 'C:\Users\Sanket\AppData\Local\Temp\hyprland-config-test-4ETbb4\openwhispr-binds.lua'
      at Object.symlinkSync (node:fs:1853:11)
      at D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:167:8
      at fixture (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:35:12)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandConfigPersistence.test.js:163:3)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
```

## test/helpers/hyprlandShortcut.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **keeps an existing dofile loader before a trailing top-level return** (`test/helpers/hyprlandShortcut.test.js:570:1`)

```text
AssertionError [ERR_ASSERTION]: The input did not match the regular expression /dofile\(/. Input:
  
  '-- lua config\n' +
    'pcall(require, "C:\\\\Users\\\\Sanket\\\\AppData\\\\Local\\\\Temp\\\\openwhispr-hyprland-test-OmWkBY\\\\config\\\\hypr\\\\openwhispr-binds.lua")\n' +
    'return {}\n' +
    '-- trailing comment\n'
  
      at D:\Teacher\OpenWhisprDictation\test\helpers\hyprlandShortcut.test.js:590:12
```

## test/helpers/linuxAutostart.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **an icon the package already installed is referenced, not copied into the user theme** (`test/helpers/linuxAutostart.test.js:171:1`)

```text
AssertionError [ERR_ASSERTION]: false == true
      at D:\Teacher\OpenWhisprDictation\test\helpers\linuxAutostart.test.js:180:12
      at async TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\linuxAutostart.test.js:29:7)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
    code: 'ERR_ASSERTION',
    actual: false,
```

## test/helpers/linuxKeyManager.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **checkAvailability is available when a single event node is readable** (`test/helpers/linuxKeyManager.test.js:237:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    {
  +   available: false,
  +   reason: 'input_access_denied'
  -   available: true
    }
```

- **checkAvailability finds a readable keyboard past a readable gamepad** (`test/helpers/linuxKeyManager.test.js:298:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    {
  +   available: false,
  +   reason: 'input_access_denied'
  -   available: true
    }
```

- **checkAvailability trusts a readable node when sysfs cannot describe it** (`test/helpers/linuxKeyManager.test.js:312:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    {
  +   available: false,
  +   reason: 'input_access_denied'
  -   available: true
    }
```

## test/helpers/linuxUrlSchemeHandler.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **a tar.gz points its handler at the launcher wrapper beside the binary** (`test/helpers/linuxUrlSchemeHandler.test.js:163:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + '"C:\\\\\\\\Users\\\\\\\\Sanket\\\\\\\\AppData\\\\\\\\Local\\\\\\\\Temp\\\\\\\\openwhispr-url-handler-test-PhCBG2\\\\\\\\install\\\\\\\\open-whispr" %U'
  - 'C:\\Users\\Sanket\\AppData\\Local\\Temp\\openwhispr-url-handler-test-PhCBG2\\install\\open-whispr %U'
  
      at D:\Teacher\OpenWhisprDictation\test\helpers\linuxUrlSchemeHandler.test.js:172:12
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\linuxUrlSchemeHandler.test.js:39:13)
```

## test/helpers/localContextBudgetIpc.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **returns the ceiling and display name for a bundled model** (`test/helpers/localContextBudgetIpc.test.js:102:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    [
      {
        modelId: 'qwen3.5-9b-q4_k_m',
  +     modelPath: '\\models\\qwen.gguf'
  -     modelPath: '/models/qwen.gguf'
```

## test/helpers/markdownMirror.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **writes reject a symlinked folder that resolves outside the mirror** (`test/helpers/markdownMirror.test.js:102:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\openwhispr-markdown-outside-GlwL8m' -> 'C:\Users\Sanket\AppData\Local\Temp\openwhispr-markdown-mirror-B1Rlvn\linked'
      at Object.symlinkSync (node:fs:1853:11)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\markdownMirror.test.js:107:6)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
      at Test.postRun (node:internal/test_runner/test:1330:19)
      at Test.run (node:internal/test_runner/test:1258:12)
```

- **writes reject a symlinked note file without changing its target** (`test/helpers/markdownMirror.test.js:116:1`)

```text
Error: EPERM: operation not permitted, symlink 'C:\Users\Sanket\AppData\Local\Temp\openwhispr-markdown-outside-KwAxUT\outside.md' -> 'C:\Users\Sanket\AppData\Local\Temp\openwhispr-markdown-mirror-Ggn2XQ\Personal\17-linked.md'
      at Object.symlinkSync (node:fs:1853:11)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\markdownMirror.test.js:126:6)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
      at Test.postRun (node:internal/test_runner/test:1330:19)
      at Test.run (node:internal/test_runner/test:1258:12)
```

## test/helpers/meetingDetectionEngine.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **a join-only card opens the meeting without recording or cooling the mic down** (`test/helpers/meetingDetectionEngine.test.js:340:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
  + []
  - [
  -   'https://meet.example/join-only'
  - ]
```

## test/helpers/meetingDetectionPreferencesIpc.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **the saved snapshot drives both detectors** (`test/helpers/meetingDetectionPreferencesIpc.test.js:100:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly deep-equal:
  + actual - expected
  
    [
      {
  +     audioDetection: false,
  -     audioDetection: true,
        processDetection: false
```

## test/helpers/metaActivation.test.js

Environment: SQLite binding targets Electron ABI 148; the shell Node requires ABI 141.

- **durable queue sends 199 then 1, caps expansion, and retires at the server milestone** (`test/helpers/metaActivation.test.js:76:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **offline retry/restart retains original event id and occurrence time** (`test/helpers/metaActivation.test.js:91:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **unresolved recognition fences watermarks and cancelled work adds no words** (`test/helpers/metaActivation.test.js:102:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **account replacement cannot adopt a capture or acknowledge its old queue** (`test/helpers/metaActivation.test.js:116:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **offline process restart cannot fabricate a source time from a stale monotonic clock** (`test/helpers/metaActivation.test.js:133:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **close proves stream complete; account erasure removes all dedicated local state** (`test/helpers/metaActivation.test.js:141:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **dictation before registration stays outside the prospective tracked count** (`test/helpers/metaActivation.test.js:186:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **an unenrolled device registers on dictation, not on the 30 s timer** (`test/helpers/metaActivation.test.js:195:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **the timer retries a registration whose answer was lost** (`test/helpers/metaActivation.test.js:210:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **a 403 quiets the timer only for an unregistered stream** (`test/helpers/metaActivation.test.js:221:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **storage failure cannot be erased by finalizer cancellation or clean shutdown** (`test/helpers/metaActivation.test.js:244:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **clean quit with unfinished recognition reports a coverage gap** (`test/helpers/metaActivation.test.js:261:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **device erasure closes queue database and disables future sync** (`test/helpers/metaActivation.test.js:271:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **close waits for a closing acknowledgement, not an earlier open batch** (`test/helpers/metaActivation.test.js:312:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

- **erasing an account's failed capture cannot suppress another account** (`test/helpers/metaActivation.test.js:336:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

## test/helpers/orukeetDictationIpc.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **the language fallback upload carries the fallback reason and detection, and no language** (`test/helpers/orukeetDictationIpc.test.js:432:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\orukeetDictationIpc.test.js:443:10)
      at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
```

- **server telemetry survives streaming usage, fallback upload and cloud cleanup IPC** (`test/helpers/orukeetDictationIpc.test.js:597:1`)

```text
TypeError: Cannot read properties of undefined (reading '1')
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\orukeetDictationIpc.test.js:629:42)
      at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7)
```

## test/helpers/parakeetDeploymentTarget.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **validates the ONNX Runtime library the sherpa binaries load** (`test/helpers/parakeetDeploymentTarget.test.js:63:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + '\\tmp\\OpenWhispr.app\\Contents\\Resources\\bin'
  - '/tmp/OpenWhispr.app/Contents/Resources/bin'
  
      at readDirectory (D:\Teacher\OpenWhisprDictation\test\helpers\parakeetDeploymentTarget.test.js:67:14)
      at Object.verifyPackagedMacosParakeet (D:\Teacher\OpenWhisprDictation\scripts\download-sherpa-onnx.js:207:8)
```

## test/helpers/permissionGuideManager.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **actions reject stale steps and drag only the packaged application** (`test/helpers/permissionGuideManager.test.js:437:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'D:\\Applications\\OpenWhispr.app'
  - '/Applications/OpenWhispr.app'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\permissionGuideManager.test.js:456:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/reasoningModelMemory.test.js

Changed local defaults conflict with upstream cloud/provider default or migration expectations.

- **retired cloud model selections are repointed to the provider default** (`test/helpers/reasoningModelMemory.test.js:131:1`)

```text
AssertionError [ERR_ASSERTION]: a registry-retired model must be repointed
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\reasoningModelMemory.test.js:153:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
    code: 'ERR_ASSERTION',
    actual: 'meta-llama/llama-4-scout-17b-16e-instruct',
    expected: 'meta-llama/llama-4-scout-17b-16e-instruct',
```

## test/helpers/retryTranscriptionHandler.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **retry: no speech from OpenWhispr Cloud is translated like a local engine's** (`test/helpers/retryTranscriptionHandler.test.js:549:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + undefined
  - 'NO_SPEECH_DETECTED'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\retryTranscriptionHandler.test.js:559:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **retry: a chunked cloud retry that lost a chunk saves the rest and returns the warning** (`test/helpers/retryTranscriptionHandler.test.js:593:1`)

```text
AssertionError [ERR_ASSERTION]: {"success":false,"error":"All chunks failed to transcribe"}
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\retryTranscriptionHandler.test.js:602:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
```

- **retry: a clean chunked cloud retry reports no warning** (`test/helpers/retryTranscriptionHandler.test.js:608:1`)

```text
AssertionError [ERR_ASSERTION]: {"success":false,"error":"All chunks failed to transcribe"}
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\retryTranscriptionHandler.test.js:610:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
```

- **file IPCs preserve dictation when uploads are disabled, including cloud source metadata** (`test/helpers/retryTranscriptionHandler.test.js:1029:1`)

```text
AssertionError [ERR_ASSERTION]: transcribe-audio-file-cloud
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\retryTranscriptionHandler.test.js:1076:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: false,
```

## test/helpers/settingsStoreApiKeyUpdates.test.js

Removed remote/assistant/meeting/account behavior or its old fixture. Remote routes must remain disabled.

- **a changed key re-warms streaming dictation without opening the mic** (`test/helpers/settingsStoreApiKeyUpdates.test.js:129:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  0 !== 1
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\settingsStoreApiKeyUpdates.test.js:161:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

## test/helpers/settingsStoreMeetingFollowFlags.test.js

Changed local defaults conflict with upstream cloud/provider default or migration expectations.

- **a fresh install gets the default modes from the copy and nothing else** (`test/helpers/settingsStoreMeetingFollowFlags.test.js:187:11`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'local'
  - 'openwhispr'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\settingsStoreMeetingFollowFlags.test.js:191:14)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/settingsStoreRetiredGroqModels.test.js

Changed local defaults conflict with upstream cloud/provider default or migration expectations.

- **groq scopes remap, other providers keep their model** (`test/helpers/settingsStoreRetiredGroqModels.test.js:29:11`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'llama-3.3-70b-versatile'
  - 'openai/gpt-oss-120b'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\settingsStoreRetiredGroqModels.test.js:41:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **compound selections remap under the rotated sentinel** (`test/helpers/settingsStoreRetiredGroqModels.test.js:46:11`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'groq/compound'
  - 'openai/gpt-oss-120b'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\settingsStoreRetiredGroqModels.test.js:58:12)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/helpers/systemTar.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **kills and rejects a tar process that does not exit before the timeout** (`test/helpers/systemTar.test.js:105:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\systemTar.test.js:116:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

- **rejects after the kill grace period when the killed process never closes** (`test/helpers/systemTar.test.js:119:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  
  false !== true
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\systemTar.test.js:131:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
      at async Test.processPendingSubtests (node:internal/test_runner/test:831:7) {
    generatedMessage: true,
```

## test/helpers/windowManagerAssistantPanel.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **assistant panel links open in the browser, never an in-app window or a local file** (`test/helpers/windowManagerAssistantPanel.test.js:243:1`)

```text
AssertionError [ERR_ASSERTION]: only the app's own reload may navigate the window
  
  3 !== 2
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\helpers\windowManagerAssistantPanel.test.js:276:10)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.processPendingSubtests (node:internal/test_runner/test:831:18)
```

## test/hooks/noteEditSurfaces.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **assistant panel, byok, fresh: edit the summary without opening email** (`test/hooks/noteEditSurfaces.test.js:42:7`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'chatIntelligence'
  - 'dictationAgent'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\hooks\noteEditSurfaces.test.js:249:18)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **assistant panel, byok, after email: edit the summary without opening email** (`test/hooks/noteEditSurfaces.test.js:42:7`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'chatIntelligence'
  - 'dictationAgent'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\hooks\noteEditSurfaces.test.js:249:18)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/locales/translationCoverage.test.js

Known localization limitation: new derivative strings use the documented English fallback.

- **every en key is present in every other language** (`test/locales/translationCoverage.test.js:139:1`)

```text
AssertionError [ERR_ASSERTION]: ar/translation is missing:
  dictationApp.title
  dictationApp.subtitle
  dictationApp.openSettings
  dictationApp.ready
  dictationApp.pressPrefix
  dictationApp.pressSuffix
  dictationApp.insertedHint
```

## test/services/assistantNoteUndo.test.js

Environment: SQLite binding targets Electron ABI 148; the shell Node requires ABI 141.

- **safe assistant edits and atomic Undo** (`test/services/assistantNoteUndo.test.js:11:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

## test/services/cleanupOutputValidation.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **history retry keeps the raw row on rejected cleanup, flags partials** (`test/services/cleanupOutputValidation.test.js:108:11`)

```text
AssertionError [ERR_ASSERTION]: the history retry callback must be present
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\services\cleanupOutputValidation.test.js:139:12)
      at Test.runInAsyncScope (node:async_hooks:226:14)
      at Test.run (node:internal/test_runner/test:1201:25)
      at Test.start (node:internal/test_runner/test:1096:17)
      at TestContext.test (node:internal/test_runner/test:377:20)
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\services\cleanupOutputValidation.test.js:108:11)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

## test/services/noteEditPersistence.test.js

Environment: SQLite binding targets Electron ABI 148; the shell Node requires ABI 141.

- **note edits preserve separate stored fields, reopen correctly, and report failed saves** (`test/services/noteEditPersistence.test.js:16:1`)

```text
Error: The module '\\?\D:\Teacher\OpenWhisprDictation\node_modules\better-sqlite3\build\Release\better_sqlite3.node'
  was compiled against a different Node.js version using
  NODE_MODULE_VERSION 148. This version of Node.js requires
  NODE_MODULE_VERSION 141. Please try re-compiling or re-installing
  the module (for instance, using `npm rebuild` or `npm install`).
      at Object..node (node:internal/modules/cjs/loader:1996:18)
      at Module.load (node:internal/modules/cjs/loader:1552:32)
      at Module._load (node:internal/modules/cjs/loader:1354:12)
```

## test/stores/enterpriseIdentityStoreImports.test.js

Environment/platform assumptions: Windows paths, POSIX permissions/sockets/symlinks, or Node 25 globals. Not repaired in this pass.

- **settingsStore imports without a bare localStorage global** (`test/stores/enterpriseIdentityStoreImports.test.js:37:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'object'
  - 'undefined'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\stores\enterpriseIdentityStoreImports.test.js:38:10)
      at Test.runInAsyncScope (node:async_hooks:226:14)
```

## test/stores/policyEffectiveVisionOverride.test.js

Unresolved legacy assertion outside the supported dictation gate. This report does not certify it harmless or prove its root cause.

- **a screenshot command stays on the cloud with its screenshot** (`test/stores/policyEffectiveVisionOverride.test.js:74:11`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'chatIntelligence'
  - 'dictationAgent'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\stores\policyEffectiveVisionOverride.test.js:81:12)
      at Test.runInAsyncScope (node:async_hooks:226:14)
```

- **a forbidden vision mode cannot redirect a local assistant to Cloud** (`test/stores/policyEffectiveVisionOverride.test.js:87:1`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'chatIntelligence'
  - 'dictationAgent'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\stores\policyEffectiveVisionOverride.test.js:111:10)
      at async Test.run (node:internal/test_runner/test:1208:7)
```

- **the override goes inert instead of routing to a keyless default** (`test/stores/policyEffectiveVisionOverride.test.js:193:11`)

```text
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:
  + actual - expected
  
  + 'chatIntelligence'
  - 'dictationAgent'
  
      at TestContext.<anonymous> (D:\Teacher\OpenWhisprDictation\test\stores\policyEffectiveVisionOverride.test.js:200:12)
      at Test.runInAsyncScope (node:async_hooks:226:14)
```

## Additional failed parent cases from the live reporter

- local Whisper recovers dictionary prompt echoes and fragments
- dictation cleanup carries the tone for the app it was captured in
- Note Recording modes survive the follow-flag migration
- retired groq model selections migrate to served replacements
- cleanup validates completed provider output using the request's prompt settings
- a managed policy never invents a target for an unconfigured vision override
- a policy that moves a configured override's provider clears its model
