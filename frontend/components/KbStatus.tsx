"use client";

import { useEffect, useState } from "react";
import { Database, AlertTriangle, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import type { KnowledgeBaseStatus } from "@/lib/types";
import { Badge } from "./ui/badge";

export function KbStatus() {
  const [status, setStatus] = useState<KnowledgeBaseStatus | null>(null);
  const [llmReady, setLlmReady] = useState<boolean | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .status()
      .then(setStatus)
      .catch(() => setError(true));
    api
      .models()
      .then((m) => setLlmReady(m.llm_ready))
      .catch(() => setLlmReady(false));
  }, []);

  if (error) {
    return (
      <Badge tone="error">
        <AlertTriangle className="h-3 w-3" /> Backend offline
      </Badge>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {status ? (
        status.connected && status.points > 0 ? (
          <Badge tone="success">
            <Database className="h-3 w-3" />
            {status.points.toLocaleString()} chunks · {status.mode}
          </Badge>
        ) : (
          <Badge tone="warning">
            <AlertTriangle className="h-3 w-3" />
            KB empty — using seed patterns
          </Badge>
        )
      ) : (
        <Badge tone="muted">Checking KB…</Badge>
      )}
      {llmReady !== null &&
        (llmReady ? (
          <Badge tone="default">
            <CheckCircle2 className="h-3 w-3" /> LLM ready
          </Badge>
        ) : (
          <Badge tone="warning">
            <AlertTriangle className="h-3 w-3" /> Set OPENROUTER_API_KEY
          </Badge>
        ))}
    </div>
  );
}
