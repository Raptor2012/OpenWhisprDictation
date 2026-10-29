import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useHotkey } from "../hooks/useHotkey";
import { useSettings } from "../hooks/useSettings";
import { formatHotkeyListLabel } from "../utils/hotkeys";
import { initializeTranscriptions, useTranscriptions } from "../stores/transcriptionStore";
import { extractCorrectionPairs } from "../utils/correctionLearner";
import { addAlias } from "../utils/vocabularyAliases";
import { useToast } from "./ui/useToast";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

const SettingsModal = React.lazy(() => import("./SettingsModal"));
const DictionaryView = React.lazy(() => import("./DictionaryView"));

interface ControlPanelProps {
  initialSettingsSection?: string;
}

interface CorrectionProposal {
  heard: string;
  corrected: string;
  addWord: boolean;
  addAlias: boolean;
}

/**
 * Explicit, user-confirmed vocabulary learning. The only text ever read is the
 * app's own transcript as edited here; nothing is observed in other apps.
 */
function LatestDictation() {
  const { t } = useTranslation();
  const { toast, dismiss } = useToast();
  const { customDictionary, updateCustomDictionary, snippets, setSnippets } = useSettings();
  const history = useTranscriptions();
  const latest = history[0];
  const latestText = latest?.text ?? "";

  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [proposals, setProposals] = useState<CorrectionProposal[] | null>(null);

  // A newer dictation replaces whatever was being corrected.
  useEffect(() => {
    setEditing(false);
    setDraft(latestText);
    setProposals(null);
    setCopied(false);
  }, [latest?.id, latestText]);

  const startEdit = useCallback(() => {
    setDraft(latestText);
    setProposals(null);
    setEditing(true);
  }, [latestText]);

  const suggest = useCallback(() => {
    const pairs = extractCorrectionPairs(latestText, draft, customDictionary);
    setProposals(
      pairs.map((pair) => ({
        heard: pair.heard,
        corrected: pair.corrected,
        addWord: true,
        addAlias: pair.heard.toLowerCase() !== pair.corrected.toLowerCase(),
      }))
    );
  }, [latestText, draft, customDictionary]);

  const applyProposals = useCallback(() => {
    if (!proposals) return;
    const words = proposals.filter((p) => p.addWord).map((p) => p.corrected);
    const aliases = proposals.filter((p) => p.addWord && p.addAlias);
    const previousSnippets = snippets;
    if (words.length > 0) updateCustomDictionary({ add: words });
    if (aliases.length > 0) {
      let next = snippets;
      for (const pair of aliases) next = addAlias(next, pair.heard, pair.corrected);
      if (next !== snippets) setSnippets(next);
    }
    setProposals(null);
    setEditing(false);
    if (words.length === 0) return;
    const toastId = toast({
      title: t("dictationApp.correction.added", { count: words.length }),
      variant: "success",
      duration: 8000,
      actions: [
        {
          label: t("dictationApp.correction.undo"),
          onClick: () => {
            updateCustomDictionary({ remove: words });
            if (aliases.length > 0) setSnippets(previousSnippets);
            dismiss(toastId);
          },
        },
      ],
    });
  }, [proposals, snippets, updateCustomDictionary, setSnippets, toast, dismiss, t]);

  const toggleProposal = useCallback(
    (index: number, field: "addWord" | "addAlias", value: boolean) => {
      setProposals((current) =>
        current
          ? current.map((p, i) =>
              i === index
                ? { ...p, [field]: value, ...(field === "addWord" && !value ? { addAlias: false } : {}) }
                : p
            )
          : current
      );
    },
    []
  );

  const anySelected = useMemo(() => proposals?.some((p) => p.addWord) ?? false, [proposals]);

  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-semibold">{t("dictationApp.latest")}</h2>
        {latestText && !editing && (
          <div className="flex items-center gap-3">
            <button
              className="text-sm text-muted-foreground hover:text-foreground"
              onClick={startEdit}
            >
              {t("dictationApp.correction.edit")}
            </button>
            <button
              className="text-sm text-muted-foreground hover:text-foreground"
              onClick={() => {
                void window.electronAPI?.writeClipboard?.(latestText);
                setCopied(true);
              }}
            >
              {copied ? t("dictationApp.copied") : t("dictationApp.copy")}
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="rounded-xl border p-4">
          <p className="mb-2 text-xs text-muted-foreground">{t("dictationApp.correction.editHint")}</p>
          <Textarea
            dir="auto"
            autoFocus
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setProposals(null);
            }}
            rows={4}
            className="text-sm"
          />
          {proposals && proposals.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">{t("dictationApp.correction.none")}</p>
          )}
          {proposals && proposals.length > 0 && (
            <div className="mt-4 rounded-lg border bg-muted/30 p-3">
              <p className="text-sm font-medium">{t("dictationApp.correction.proposeTitle")}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("dictationApp.correction.proposeDescription")}
              </p>
              <ul className="mt-3 space-y-2">
                {proposals.map((p, index) => (
                  <li key={`${p.heard}-${p.corrected}`} className="text-sm">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={p.addWord}
                        onChange={(e) => toggleProposal(index, "addWord", e.target.checked)}
                      />
                      <span dir="auto" className="font-medium">
                        {p.corrected}
                      </span>
                    </label>
                    {p.heard.toLowerCase() !== p.corrected.toLowerCase() && (
                      <label className="ms-6 mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={p.addAlias}
                          disabled={!p.addWord}
                          onChange={(e) => toggleProposal(index, "addAlias", e.target.checked)}
                        />
                        <span dir="auto">
                          {t("dictationApp.correction.alsoAlias", { heard: p.heard })}
                        </span>
                      </label>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(false);
                setProposals(null);
              }}
            >
              {t("dictationApp.correction.cancel")}
            </Button>
            {proposals && proposals.length > 0 ? (
              <Button size="sm" onClick={applyProposals} disabled={!anySelected}>
                {t("dictationApp.correction.addSelected")}
              </Button>
            ) : (
              <Button size="sm" onClick={suggest} disabled={draft.trim() === latestText.trim()}>
                {t("dictationApp.correction.suggest")}
              </Button>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border p-5 text-sm whitespace-pre-wrap" aria-live="polite" dir="auto">
          {latestText || t("dictationApp.emptyHistory")}
        </div>
      )}
    </section>
  );
}

export default function ControlPanel({ initialSettingsSection }: ControlPanelProps = {}) {
  const { t } = useTranslation();
  const { hotkey } = useHotkey();
  const [section, setSection] = useState(initialSettingsSection || "general");
  const [settingsOpen, setSettingsOpen] = useState(Boolean(initialSettingsSection));
  const [dictionaryOpen, setDictionaryOpen] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    void initializeTranscriptions(10).catch(() => setLoadError(true));
    const openSettings = async () => {
      const requested = await window.electronAPI?.getPendingSettingsSection?.();
      setSection(requested || "general");
      setSettingsOpen(true);
    };
    const unsubscribe = window.electronAPI?.onShowSettings?.(() => void openSettings());
    return () => unsubscribe?.();
  }, []);

  const openSettings = (next: string) => {
    setSection(next);
    setSettingsOpen(true);
  };

  const quickLinks: Array<{ key: string; section?: string; onClick?: () => void }> = [
    { key: "microphone", section: "general" },
    { key: "keyboardMouse", section: "hotkeys" },
    { key: "speechModel", section: "transcription" },
    { key: "cleanupModel", section: "llms" },
    { key: "dictionary", onClick: () => setDictionaryOpen(true) },
  ];

  return (
    <main className="h-screen overflow-auto bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <header className="mb-8 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t("dictationApp.title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("dictationApp.subtitle")}</p>
          </div>
          <button
            className="rounded-lg border px-4 py-2 text-sm hover:bg-muted"
            onClick={() => openSettings("general")}
          >
            {t("dictationApp.openSettings")}
          </button>
        </header>

        {dictionaryOpen ? (
          <section>
            <button
              className="mb-4 text-sm text-muted-foreground hover:text-foreground"
              onClick={() => setDictionaryOpen(false)}
            >
              ← {t("dictationApp.backToDictation")}
            </button>
            <Suspense fallback={<p>{t("dictationApp.loadingDictionary")}</p>}>
              <DictionaryView />
            </Suspense>
          </section>
        ) : (
          <>
            <section className="rounded-xl border bg-card p-6">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t("dictationApp.ready")}
              </p>
              <p className="mt-3 text-lg">
                {t("dictationApp.pressPrefix")}{" "}
                <kbd className="rounded border bg-muted px-2 py-1 font-mono text-sm">
                  {formatHotkeyListLabel(hotkey)}
                </kbd>{" "}
                {t("dictationApp.pressSuffix")}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{t("dictationApp.insertedHint")}</p>
            </section>
            <div className="mt-5 flex flex-wrap gap-2">
              {quickLinks.map((link) => (
                <button
                  key={link.key}
                  className="rounded-lg border px-3 py-2 text-sm hover:bg-muted"
                  onClick={link.onClick ?? (() => openSettings(link.section!))}
                >
                  {t(`dictationApp.${link.key}`)}
                </button>
              ))}
            </div>
            {loadError ? (
              <p className="mt-8 text-sm text-muted-foreground">{t("dictationApp.historyError")}</p>
            ) : (
              <LatestDictation />
            )}
          </>
        )}
      </div>
      {settingsOpen && (
        <Suspense fallback={null}>
          <SettingsModal
            key={section}
            open={settingsOpen}
            onOpenChange={setSettingsOpen}
            initialSection={section}
          />
        </Suspense>
      )}
    </main>
  );
}
