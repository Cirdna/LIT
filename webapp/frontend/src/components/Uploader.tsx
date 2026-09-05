import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

type ResultRow = { filename: string; status: string; duplicate?: boolean; error?: string };

export function Uploader({ variant = "hero" }: { variant?: "hero" | "compact" }) {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [results, setResults] = useState<ResultRow[] | null>(null);

  const mutation = useMutation({
    mutationFn: (files: File[]) => api.upload(files),
    onSuccess: (rows) => {
      setResults(rows);
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
  });

  const submit = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setResults(null);
    mutation.mutate(Array.from(files));
  };

  const accept = ".pdf,.docx,.png,.jpg,.jpeg,.tiff,.txt";

  if (variant === "compact") {
    return (
      <div className="flex items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept}
          className="hidden"
          onChange={(e) => submit(e.target.files)}
        />
        <button className="btn btn-primary" onClick={() => inputRef.current?.click()} disabled={mutation.isPending}>
          {mutation.isPending ? "Uploading…" : "Upload contracts"}
        </button>
        {results && <UploadSummary results={results} />}
      </div>
    );
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          submit(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        className={`panel flex cursor-pointer flex-col items-center justify-center gap-2 px-6 py-16 text-center transition-colors ${
          dragOver ? "border-navy bg-okbg" : "hover:bg-paper"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={accept}
          className="hidden"
          onChange={(e) => submit(e.target.files)}
        />
        <p className="text-2xl font-semibold text-ink">Drop a folder of contracts here</p>
        <p className="max-w-md text-muted">
          Or click to choose files. AITHENA reads each one, pulls out the dates and obligations, and tells you what
          needs acting on — with a citation for every value.
        </p>
        <p className="mt-2 text-sm text-faint">PDF, DOCX, PNG, JPG, TIFF, TXT · up to 50 MB each</p>
        {mutation.isPending && <p className="mt-2 font-medium text-navy">Uploading…</p>}
      </div>
      {results && (
        <div className="mt-3">
          <UploadSummary results={results} />
        </div>
      )}
      {mutation.isError && <p className="mt-2 text-alert">{(mutation.error as Error).message}</p>}
    </div>
  );
}

function UploadSummary({ results }: { results: ResultRow[] }) {
  const created = results.filter((r) => !r.duplicate && r.status !== "unsupported").length;
  const dupes = results.filter((r) => r.duplicate).length;
  const bad = results.filter((r) => r.status === "unsupported").length;
  return (
    <div className="text-sm text-muted">
      {created > 0 && <span className="mr-3 text-ink">{created} added</span>}
      {dupes > 0 && <span className="mr-3">{dupes} already uploaded</span>}
      {bad > 0 && <span className="text-alert">{bad} not supported</span>}
    </div>
  );
}
