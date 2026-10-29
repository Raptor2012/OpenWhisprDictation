import type { Snippet } from "./snippets";

/**
 * Spoken aliases for dictionary words ("heard as" forms) are stored as snippets:
 * the alias is the trigger and the preferred spelling is the replacement. They
 * are expanded by the same whole-word, case-insensitive pass that handles every
 * other snippet, so a misheard "sunk it" becomes "Sanket" before cleanup runs.
 */

function normalize(value: string): string {
  return value.trim().normalize("NFC").toLowerCase();
}

/** Aliases whose replacement is exactly `word` (case-insensitive). */
export function aliasesForWord(word: string, snippets: Snippet[] | null | undefined): string[] {
  const target = normalize(word);
  if (!target) return [];
  return (snippets ?? [])
    .filter((snippet) => normalize(snippet.replacement) === target)
    .map((snippet) => snippet.trigger);
}

/** Whether `alias` is already a trigger for any snippet. */
export function aliasExists(alias: string, snippets: Snippet[] | null | undefined): boolean {
  const key = normalize(alias);
  return !!key && (snippets ?? []).some((snippet) => normalize(snippet.trigger) === key);
}

/**
 * Add `alias` → `word`. Rejects an empty alias, an alias equal to the word
 * itself (it would replace a word with itself) and a trigger that is already
 * taken, returning the input list unchanged in those cases.
 */
export function addAlias(snippets: Snippet[] | null | undefined, alias: string, word: string): Snippet[] {
  const list = snippets ?? [];
  const trigger = alias.trim();
  const replacement = word.trim();
  if (!trigger || !replacement) return list;
  if (normalize(trigger) === normalize(replacement)) return list;
  if (aliasExists(trigger, list)) return list;
  return [...list, { trigger, replacement }];
}

export function removeAlias(snippets: Snippet[] | null | undefined, alias: string): Snippet[] {
  const key = normalize(alias);
  return (snippets ?? []).filter((snippet) => normalize(snippet.trigger) !== key);
}

/** After a dictionary word is renamed, its aliases point at the new spelling. */
export function retargetAliases(
  snippets: Snippet[] | null | undefined,
  previousWord: string,
  nextWord: string
): Snippet[] {
  const from = normalize(previousWord);
  const to = nextWord.trim();
  if (!from || !to) return snippets ?? [];
  return (snippets ?? []).map((snippet) =>
    normalize(snippet.replacement) === from ? { ...snippet, replacement: to } : snippet
  );
}

/** After a dictionary word is removed, its aliases go with it. */
export function removeWordAliases(snippets: Snippet[] | null | undefined, word: string): Snippet[] {
  const target = normalize(word);
  if (!target) return snippets ?? [];
  return (snippets ?? []).filter((snippet) => normalize(snippet.replacement) !== target);
}
