function localDictationAllowed(settings, managed) {
  return settings.useLocalWhisper === true && !managed;
}
function localCleanupAllowed(cleanup, agentRequested, translationRequested) {
  return cleanup.mode === "local" && !agentRequested && !translationRequested;
}
export { localDictationAllowed, localCleanupAllowed };
export default { localDictationAllowed, localCleanupAllowed };
