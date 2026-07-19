"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useProposalStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Badge } from "@/components/ui/badge";

export default function SettingsPage() {
  const store = useProposalStore();
  const [models, setModels] = useState<string[]>([]);
  const [status, setStatus] = useState<{
    api_key_set: boolean;
    gemini_api_key_set: boolean;
    grok_api_key_set: boolean;
    source: "runtime" | "env" | "none";
    default_model: string;
    models: string[];
  } | null>(null);
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [groqKey, setGroqKey] = useState("");
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [detail, setDetail] = useState<string>("");
  const [error, setError] = useState<string>("");

  function selectedProviderLabel() {
    if (store.model.startsWith("groq/")) return "Groq";
    if (store.model.startsWith("openrouter/")) return "OpenRouter";
    return "LLM";
  }

  function selectedProviderKey() {
    if (store.model.startsWith("groq/")) return groqKey.trim();
    return openrouterKey.trim();
  }

  useEffect(() => {
    if (typeof window !== "undefined") {
      setOpenrouterKey(window.localStorage.getItem("proposal-copilot-openrouter-key") || "");
      setGeminiKey(window.localStorage.getItem("proposal-copilot-gemini-key") || "");
      // Groq credentials were intentionally revoked. Remove both the current
      // and legacy browser storage names so an old key cannot be reused.
      window.localStorage.removeItem("proposal-copilot-groq-key");
      window.localStorage.removeItem("proposal-copilot-grok-key");
      setGroqKey("");
    }
    api.models().then((m) => {
      setModels(m.models);
      if (!m.models.includes(store.model)) {
        store.setModel(m.default);
      }
    });
    api
      .getOpenRouterSettings()
      .then((value) => {
        setStatus(value);
        if (value.models?.length) {
          setModels((prev) => (prev.length ? prev : value.models));
        }
      })
      .catch(() => setStatus(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function persistKeys(nextOpenRouter: string, nextGemini: string, nextGroq: string) {
    const payload = {
      api_key: nextOpenRouter.trim(),
      gemini_api_key: nextGemini.trim(),
      grok_api_key: nextGroq.trim(),
    };
    if (typeof window !== "undefined") {
      if (payload.api_key) window.localStorage.setItem("proposal-copilot-openrouter-key", payload.api_key);
      else window.localStorage.removeItem("proposal-copilot-openrouter-key");
      if (payload.gemini_api_key) window.localStorage.setItem("proposal-copilot-gemini-key", payload.gemini_api_key);
      else window.localStorage.removeItem("proposal-copilot-gemini-key");
      if (payload.grok_api_key) {
        window.localStorage.setItem("proposal-copilot-groq-key", payload.grok_api_key);
        window.localStorage.setItem("proposal-copilot-grok-key", payload.grok_api_key);
      } else {
        window.localStorage.removeItem("proposal-copilot-groq-key");
        window.localStorage.removeItem("proposal-copilot-grok-key");
      }
    }
    return api.saveOpenRouterSettings(payload);
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await persistKeys(openrouterKey, geminiKey, groqKey);
      setStatus(updated);
      setMessage("LLM keys saved.");
      setDetail(
        [
          `OpenRouter: ${updated.api_key_set ? "saved" : "empty"}.`,
          `Gemini: ${updated.gemini_api_key_set ? "saved" : "empty"}.`,
          `Groq: ${updated.grok_api_key_set ? "saved" : "empty"}.`,
          `Source: ${updated.source}. Default model: ${updated.default_model}.`,
        ].join(" ")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save LLM settings.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCheck(apiKey = selectedProviderKey()) {
    setChecking(true);
    setError("");
    setMessage("");
    setDetail("");
    try {
      const trimmed = apiKey.trim();
      const result = await api.checkOpenRouterSettings({
        api_key: store.model.startsWith("groq/") ? "" : trimmed,
        grok_api_key: store.model.startsWith("groq/") ? trimmed : "",
        model: store.model,
      });
      setMessage(result.ok ? result.message : result.message || `${selectedProviderLabel()} check failed.`);
      setDetail(result.detail || `Model checked: ${result.model}.`);
      setStatus({
        api_key_set: result.ok,
        gemini_api_key_set: Boolean(geminiKey.trim()),
        grok_api_key_set: Boolean(groqKey.trim()),
        source: result.source === "request" ? "runtime" : result.source,
        default_model: result.model || "groq/openai/gpt-oss-20b",
        models: models.length ? models : [result.model].filter(Boolean),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to check ${selectedProviderLabel()} settings.`);
    } finally {
      setChecking(false);
    }
  }

  async function handleSaveAndCheck() {
    setSaving(true);
    setChecking(true);
    setError("");
    try {
      const updated = await persistKeys(openrouterKey, geminiKey, groqKey);
      setStatus(updated);
      const selectedKey = selectedProviderKey();
      const result = await api.checkOpenRouterSettings({
        api_key: store.model.startsWith("groq/") ? "" : selectedKey,
        grok_api_key: store.model.startsWith("groq/") ? selectedKey : "",
        model: store.model,
      });
      setMessage(result.ok ? result.message : result.message || `${selectedProviderLabel()} check failed.`);
      setDetail(result.detail || `Source: ${updated.source}.`);
      setStatus({
        api_key_set: result.ok,
        gemini_api_key_set: Boolean(geminiKey.trim()),
        grok_api_key_set: Boolean(groqKey.trim()),
        source: updated.source,
        default_model: updated.default_model,
        models: updated.models.length ? updated.models : models,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to save and check ${selectedProviderLabel()} settings.`);
    } finally {
      setSaving(false);
      setChecking(false);
    }
  }

  const working = status?.api_key_set && !message.toLowerCase().includes("failed");
  const blocked = !working && (status?.source === "none" || message.length > 0 || error.length > 0);

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Configure provider keys once and reuse them for generation, docs queries, and RFP parsing.
            The selected model determines which provider key is checked and used for live generation.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={working ? "success" : blocked ? "warning" : "muted"}>
            {working ? <CheckCircle2 className="h-3 w-3" /> : blocked ? <AlertTriangle className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
            {working ? "Live LLM ready" : blocked ? "Generation blocked" : "Not checked"}
          </Badge>
          {status ? (
            <Badge tone="default">
              Source: {status.source}
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <section className="rounded-3xl border border-border bg-card p-6 shadow-sm">
          <div className="mb-5 flex items-center gap-3">
            <div className="rounded-2xl bg-primary/10 p-3 text-primary">
              <KeyRound className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">LLM configuration</h2>
              <p className="text-sm text-muted-foreground">
                Save keys once and the app will use the key that matches the selected model.
              </p>
            </div>
          </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label>OpenRouter API Key</Label>
                <Input
                  type="password"
                  value={openrouterKey}
                  onChange={(e) => setOpenrouterKey(e.target.value)}
                  placeholder="sk-or-v1-..."
                />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Gemini API Key</Label>
                  <Input
                    type="password"
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    placeholder="Gemini key"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Groq API Key</Label>
                  <Input
                    type="password"
                    value={groqKey}
                    onChange={(e) => setGroqKey(e.target.value)}
                    placeholder="Groq key"
                  />
                </div>
              </div>

            <div className="space-y-2">
              <Label>Preferred model</Label>
              <Select value={store.model} onChange={(e) => store.setModel(e.target.value)}>
                {models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </Select>
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              <Button onClick={() => void handleSaveAndCheck()} disabled={saving || checking}>
                {saving || checking ? <Spinner /> : null}
                Save and check
              </Button>
              <Button variant="outline" onClick={() => void handleSave()} disabled={saving}>
                {saving ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
                Save only
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setOpenrouterKey("");
                  setGeminiKey("");
                  setGroqKey("");
                  void (async () => {
                    await persistKeys("", "", "");
                    await handleCheck("");
                  })();
                }}
                disabled={saving || checking}
              >
                Clear key
              </Button>
              <Button variant="ghost" onClick={() => void handleCheck()} disabled={checking}>
                {checking ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                Check current
              </Button>
            </div>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {message ? (
              <div className="rounded-2xl border border-border bg-muted/40 p-4 text-sm">
                <div className="font-medium">{message}</div>
                {detail ? <div className="mt-1 text-muted-foreground">{detail}</div> : null}
              </div>
            ) : null}

            <div className="grid gap-3 md:grid-cols-3">
              <KeyStatus label="OpenRouter" active={Boolean(status?.api_key_set)} />
              <KeyStatus label="Gemini" active={Boolean(status?.gemini_api_key_set)} />
              <KeyStatus label="Groq" active={Boolean(status?.grok_api_key_set)} />
            </div>
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">Will it work?</h3>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                {working
                  ? "Yes. The saved key and selected model are valid, so proposal generation should use the live LLM path."
                  : blocked
                    ? "No. The app either has no usable key or the selected model/key check failed, so proposal generation is blocked."
                    : "Run a check to verify whether the current key and model will work."}
              </p>
              <p>
                There is no local synthesis fallback for proposal generation. The key and selected model must work.
              </p>
            </div>
          </section>

          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">Persistence</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>Browser localStorage keeps the key across page refreshes.</li>
              <li>The backend also stores a runtime copy when you save.</li>
              <li>OpenRouter requests send the key in a header when available.</li>
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}

function KeyStatus({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="rounded-2xl border border-border bg-background px-3 py-3 text-sm">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={active ? "mt-1 font-medium text-foreground" : "mt-1 font-medium text-muted-foreground"}>
        {active ? "Saved" : "Empty"}
      </div>
    </div>
  );
}
