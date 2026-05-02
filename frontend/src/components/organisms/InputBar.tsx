import { useState, useRef, useCallback } from "react";
import { ChatInput } from "../molecules/ChatInput";
import { ContextRing } from "../atoms/ContextRing";
import { BashConfirmBar } from "../molecules/BashConfirmBar";
import { useChat } from "../../hooks/useChat";

interface DroppedImage {
  path: string;
  preview: string;
  filename: string;
}

async function uploadImage(file: File): Promise<DroppedImage> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/api/files/upload", { method: "POST", body: form });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Upload failed (HTTP ${resp.status})`);
  }
  const data = await resp.json();
  return {
    path: data.path,
    preview: URL.createObjectURL(file),
    filename: data.filename,
  };
}

export function InputBar() {
  const {
    sendMessage,
    cancelStream,
    clearHistory,
    streaming,
    ready,
    contextPct,
    summarizing,
    summarizeContext,
  } = useChat();
  const [droppedImage, setDroppedImage] = useState<DroppedImage | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const dragCounter = useRef(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    if (e.dataTransfer.types.includes("Files")) setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current === 0) setDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    setUploading(true);
    try {
      const img = await uploadImage(file);
      setDroppedImage(img);
    } catch (err) {
      console.error("[InputBar] Image upload failed:", err);
    } finally {
      setUploading(false);
    }
  }, []);

  return (
    <div
      className={`flex flex-1 flex-shrink w-full items-center gap-2 px-3 py-3 m-2 bg-[var(--glass-bg-solid)] backdrop-blur-xl border rounded-xl z-10 transition-colors ${dragOver ? "border-[var(--accent)] bg-[var(--accent)]/10" : "border-[var(--accent)]"}`}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <ContextRing
        contextPct={contextPct}
        summarizing={summarizing}
        onSummarize={summarizeContext}
      />
      <ChatInput
        onSend={sendMessage}
        onCancel={cancelStream}
        onClear={clearHistory}
        streaming={streaming}
        disabled={!ready || uploading}
        droppedImage={droppedImage}
        onClearImage={() => setDroppedImage(null)}
      />
      <BashConfirmBar />
    </div>
  );
}
