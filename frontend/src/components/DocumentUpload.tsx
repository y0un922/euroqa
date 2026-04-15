import { Upload } from "lucide-react";
import { useCallback, useRef, useState } from "react";

type DocumentUploadProps = {
  disabled?: boolean;
  onSelectFile: (file: File) => void;
};

export default function DocumentUpload({
  disabled = false,
  onSelectFile,
}: DocumentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
        onSelectFile(file);
      }
    },
    [onSelectFile]
  );

  return (
    <div
      className={`rounded-lg border-2 border-dashed p-3 text-center transition-colors ${
        isDragOver
          ? "border-cyan-400 bg-cyan-50"
          : "border-stone-200 bg-stone-50 hover:border-stone-300"
      } ${disabled ? "pointer-events-none opacity-50" : "cursor-pointer"}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          e.target.value = "";
        }}
      />
      <Upload className="mx-auto mb-1 h-4 w-4 text-stone-400" />
      <p className="text-xs text-stone-500">
        {disabled ? "处理中…" : "上传 PDF 规范"}
      </p>
    </div>
  );
}
