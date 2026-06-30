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
    source: "runtime" | "env" | "none";
    default_model: string;
    models: string[];
  } | null>(null);
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [detail, setDetail] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (typeof window !== "undefined") {
      setOpenrouterKey(window.localStorage.getItem("proposal-copilot-openrouter-key") || "");
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

  async function persistKey(nextValue: string) {
    const trimmed = nextValue.trim();
    if (typeof window !== "undefined") {
      if (trimmed) {
        window.localStorage.setItem("proposal-copilot-openrouter-key", trimmed);
      } else {
        window.localStorage.removeItem("proposal-copilot-openrouter-key");
      }
    }
    return api.saveOpenRouterSettings({ api_key: trimmed });
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const updated = await persistKey(openrouterKey);
      setStatus(updated);
      setMessage(updated.api_key_set ? "OpenRouter key saved." : "OpenRouter key cleared.");
      setDetail(`Source: ${updated.source}. Default model: ${updated.default_model}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save OpenRouter settings.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCheck() {
    setChecking(true);
    setError("");
    setMessage("");
    setDetail("");
    try {
      const trimmed = openrouterKey.trim();
      const result = await api.checkOpenRouterSettings({ api_key: trimmed, model: store.model });
      setMessage(result.ok ? result.message : result.message || "OpenRouter check failed.");
      setDetail(result.detail || `Model checked: ${result.model}.`);
      setStatus({
        api_key_set: result.ok,
        source: result.source === "request" ? "runtime" : result.source,
        default_model: result.model || "deepseek/deepseek-chat",
        models: models.length ? models : [result.model].filter(Boolean),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check OpenRouter settings.");
    } finally {
      setChecking(false);
    }
  }

  async function handleSaveAndCheck() {
    setSaving(true);
    setChecking(true);
    setError("");
    try {
      const updated = await persistKey(openrouterKey);
      setStatus(updated);
      const result = await api.checkOpenRouterSettings({ api_key: openrouterKey.trim(), model: store.model });
      setMessage(result.ok ? result.message : result.message || "OpenRouter check failed.");
      setDetail(result.detail || `Source: ${updated.source}.`);
      setStatus({
        api_key_set: result.ok,
        source: updated.source,
        default_model: updated.default_model,
        models: updated.models.length ? updated.models : models,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save and check OpenRouter settings.");
    } finally {
      setSaving(false);
      setChecking(false);
    }
  }

  const working = status?.api_key_set && !message.toLowerCase().includes("failed");
  const fallbackLikely = status?.source === "none" || message.toLowerCase().includes("fallback");

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Configure the OpenRouter key once and reuse it for generation, docs queries, RFP parsing,
            and planner flows. The key is stored in your browser and also saved on the backend runtime
            when you click save.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={working ? "success" : fallbackLikely ? "warning" : "muted"}>
            {working ? <CheckCircle2 className="h-3 w-3" /> : fallbackLikely ? <AlertTriangle className="h-3 w-3" /> : <ShieldCheck className="h-3 w-3" />}
            {working ? "Live LLM ready" : fallbackLikely ? "Fallback likely" : "Not checked"}
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
              <h2 className="text-lg font-semibold">OpenRouter configuration</h2>
              <p className="text-sm text-muted-foreground">
                Save a key once and the app will keep using it until you change it.
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
                  void (async () => {
                    await persistKey("");
                    await handleCheck();
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
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">Will it work?</h3>
            <div className="space-y-2 text-sm text-muted-foreground">
              <p>
                {working
                  ? "Yes. The saved key and selected model are valid, so proposal generation should use the live LLM path."
                  : fallbackLikely
                    ? "Fallback is likely. The app either has no usable key or the selected model/key check failed."
                    : "Run a check to verify whether the current key and model will work."}
              </p>
              <p>
                If the check fails, proposal generation will fall back to the local synthesis path instead of OpenRouter.
              </p>
            </div>
          </section>

          <section className="rounded-3xl border border-border bg-card p-5 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold">Persistence</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li>Browser localStorage keeps the key across page refreshes.</li>
              <li>The backend also stores a runtime copy when you save.</li>
              <li>All generation requests send the key in a header when available.</li>
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}
