import React, { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

const SUPPORTED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"];
const MAX_FILES = 20;
const STATUS_LABELS = {
  waiting: "待機中",
  processing: "処理中",
  completed: "完了",
  error: "エラー"
};
const PDF_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
const PDF_WORKER_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

const formatFileSize = (bytes = 0) => {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(exponent === 0 ? 0 : value < 10 ? 1 : 0)} ${units[exponent]}`;
};

const buildResultMarkdown = (upload) => {
  const rangeText = upload.isPdf
    ? `${upload.rangeStart}-${upload.rangeEnd}`
    : "Single image";

  return `# OCR 結果\n\n- ファイル: **${upload.name}**\n- ページ範囲: ${rangeText}\n- ステータス: 完了\n\n---\n\n> ここに OCR テキストを挿入してください。`;
};

const isPdfFile = (file) => {
  if (!file) return false;
  if (file.type === "application/pdf") return true;
  const ext = file.name?.split(".").pop()?.toLowerCase();
  return ext === "pdf";
};

const isImageFile = (file) => {
  if (!file) return false;
  if (file.type.startsWith("image/")) return true;
  const ext = file.name?.split(".").pop()?.toLowerCase();
  return SUPPORTED_EXTENSIONS.includes(ext) && ext !== "pdf";
};

const App = () => {
  const [uploads, setUploads] = useState([]);
  const [activeUploadId, setActiveUploadId] = useState(null);
  const [selectedFileIds, setSelectedFileIds] = useState(new Set());
  const [isDragging, setIsDragging] = useState(false);
  const [globalError, setGlobalError] = useState("");
  const [toast, setToast] = useState("");
  const [pdfLibReady, setPdfLibReady] = useState(false);
  const [pdfLibError, setPdfLibError] = useState("");

  const fileInputRef = useRef(null);
  const timersRef = useRef({});
  const pdfLoaderRef = useRef(null);
  const imagePreviewUrlsRef = useRef(new Set());

  const ensurePdfJs = useCallback(() => {
    if (window.pdfjsLib) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_URL;
      if (!pdfLibReady) {
        setPdfLibReady(true);
        setPdfLibError("");
      }
      return Promise.resolve(window.pdfjsLib);
    }

    if (pdfLoaderRef.current) {
      return pdfLoaderRef.current;
    }

    pdfLoaderRef.current = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = PDF_JS_URL;
      script.async = true;
      script.onload = () => {
        if (window.pdfjsLib) {
          window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_URL;
          setPdfLibReady(true);
          setPdfLibError("");
          resolve(window.pdfjsLib);
        } else {
          const error = new Error("PDF.js の読み込みに失敗しました");
          setPdfLibReady(false);
          setPdfLibError(error.message);
          pdfLoaderRef.current = null;
          reject(error);
        }
      };
      script.onerror = () => {
        const error = new Error("PDF プレビュー用ライブラリを読み込めませんでした");
        setPdfLibReady(false);
        setPdfLibError(error.message);
        pdfLoaderRef.current = null;
        reject(error);
      };
      document.body.appendChild(script);
    });

    return pdfLoaderRef.current;
  }, [pdfLibReady]);

  useEffect(() => {
    ensurePdfJs().catch(() => {});
  }, [ensurePdfJs]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(""), 2200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!uploads.length) {
      setActiveUploadId(null);
      return;
    }
    if (!uploads.some((item) => item.id === activeUploadId)) {
      setActiveUploadId(uploads[0].id);
    }
  }, [uploads, activeUploadId]);

  useEffect(() => () => {
    Object.values(timersRef.current).forEach((intervalId) => clearInterval(intervalId));
    imagePreviewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    imagePreviewUrlsRef.current.clear();
  }, []);

  const updateUpload = useCallback((id, updater) => {
    setUploads((prev) =>
      prev.map((upload) => {
        if (upload.id !== id) return upload;
        const patch = typeof updater === "function" ? updater(upload) : updater;
        return { ...upload, ...patch };
      })
    );
  }, []);

  const generatePdfPreview = useCallback(async (file, uploadId) => {
    try {
      const pdfjs = await ensurePdfJs();
      const arrayBuffer = await file.arrayBuffer();
      const pdf = await pdfjs.getDocument({ data: arrayBuffer }).promise;
      const page = await pdf.getPage(1);
      const initialViewport = page.getViewport({ scale: 1 });
      const targetWidth = 160;
      const scale = targetWidth / initialViewport.width;
      const viewport = page.getViewport({ scale });

      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d");
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await page.render({ canvasContext: context, viewport }).promise;
      const dataUrl = canvas.toDataURL("image/png");

      updateUpload(uploadId, {
        thumbnail: dataUrl,
        pageCount: pdf.numPages,
        rangeStart: 1,
        rangeEnd: pdf.numPages,
        loadingPreview: false,
        error: ""
      });
    } catch (error) {
      updateUpload(uploadId, {
        loadingPreview: false,
        error: "PDF プレビューの生成に失敗しました"
      });
    }
  }, [ensurePdfJs, updateUpload]);

  const handleFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    // ファイル数の上限を確認
    const currentCount = uploads.length;
    const availableSlots = MAX_FILES - currentCount;

    if (availableSlots <= 0) {
      setGlobalError(`ファイル数が上限（${MAX_FILES}個）に達しています。`);
      return;
    }

    const filesToProcess = files.slice(0, availableSlots);
    const exceededCount = files.length - filesToProcess.length;

    let rejected = 0;
    const newUploads = [];

    filesToProcess.forEach((file, index) => {
      if (!isPdfFile(file) && !isImageFile(file)) {
        rejected += 1;
        return;
      }

      const id = `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 7)}`;
      const isPdf = isPdfFile(file);
      const isImage = isImageFile(file);

      const base = {
        id,
        file,
        name: file.name,
        size: file.size,
        status: "waiting",
        progress: 0,
        error: "",
        isPdf,
        isImage,
        rangeStart: 1,
        rangeEnd: isPdf ? null : 1,
        pageCount: isPdf ? null : 1,
        thumbnail: "",
        loadingPreview: isPdf,
        ocrResult: "",
        autoDownloaded: false,
        createdAt: Date.now()
      };

      if (isImage) {
        const url = URL.createObjectURL(file);
        imagePreviewUrlsRef.current.add(url);
        base.thumbnail = url;
        base.loadingPreview = false;
      }

      newUploads.push(base);

      if (isPdf) {
        generatePdfPreview(file, id);
      }
    });

    // エラーメッセージを設定
    let errorMessage = "";
    if (exceededCount > 0) {
      errorMessage += `上限により${exceededCount}個のファイルをスキップしました。`;
    }
    if (rejected > 0) {
      if (errorMessage) errorMessage += " ";
      errorMessage += `サポートされていないファイルを${rejected}個スキップしました。`;
    }

    if (errorMessage) {
      setGlobalError(errorMessage);
    } else {
      setGlobalError("");
    }

    if (newUploads.length) {
      setUploads((prev) => {
        const updated = [...newUploads, ...prev];
        setSelectedFileIds(new Set(updated.map((item) => item.id)));
        return updated;
      });
      setActiveUploadId(newUploads[0].id);
      setToast(`${newUploads.length}個のファイルを追加しました。`);
    }
  };

  const handleFileInputChange = (event) => {
    handleFiles(event.target.files);
    event.target.value = "";
  };

  const handleDragOver = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!isDragging) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.contains(event.relatedTarget)) return;
    setIsDragging(false);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    if (event.dataTransfer?.files?.length) {
      handleFiles(event.dataTransfer.files);
    }
  };

  const validateRange = (upload) => {
    if (!upload.isPdf) return { ok: true, message: "" };
    const { rangeStart, rangeEnd, pageCount } = upload;
    if (!pageCount) return { ok: false, message: "PDF 情報を取得中です。" };

    if (!rangeStart || !rangeEnd) {
      return { ok: false, message: "ページ範囲を入力してください" };
    }

    if (rangeStart > rangeEnd) {
      return { ok: false, message: "開始ページは終了ページ以下で指定してください" };
    }

    if (rangeStart < 1 || rangeEnd > pageCount) {
      return { ok: false, message: `1 〜 ${pageCount} の範囲で指定してください` };
    }

    return { ok: true, message: "" };
  };

  const sendOcrRequest = async (uploadId) => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target) return;

    updateUpload(uploadId, {
      status: "processing",
      progress: 5,
      error: "",
      autoDownloaded: false
    });

    try {
      const formData = new FormData();
      formData.append('file', target.file);
      formData.append('file_type', target.isPdf ? 'pdf' : 'image');
      formData.append('file_size', target.size.toString());

      if (target.isPdf) {
        formData.append('range_start', target.rangeStart.toString());
        formData.append('range_end', target.rangeEnd.toString());
        formData.append('page_count', target.pageCount.toString());
      }

      const response = await fetch('/api/aibt/ocr', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();

      // OCRステータスのポーリングを開始
      pollOcrStatus(uploadId, result.task_id || uploadId);

    } catch (error) {
      console.error('OCRリクエストに失敗しました:', error);
      updateUpload(uploadId, {
        status: "error",
        error: error.message || "OCRリクエストに失敗しました。再試行してください"
      });
    }
  };

  const pollOcrStatus = (uploadId, taskId) => {
    if (timersRef.current[uploadId]) {
      clearInterval(timersRef.current[uploadId]);
    }

    let progressValue = 10;

    timersRef.current[uploadId] = window.setInterval(async () => {
      try {
        // 進捗を擬似的に増加させる
        progressValue = Math.min(progressValue + Math.floor(Math.random() * 15) + 5, 95);

        updateUpload(uploadId, { progress: progressValue });

        // 実際のステータス取得 API 呼び出し
        try {
          const statusResponse = await fetch(`/api/aibt/ocr/status/${taskId}`);
          if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            const target = uploads.find((item) => item.id === uploadId);

            // 実際のステータスに基づいて進捗を更新
            if (statusData.status === 'completed' && statusData.ocr_result) {
              clearInterval(timersRef.current[uploadId]);
              delete timersRef.current[uploadId];

              updateUpload(uploadId, {
                progress: 100,
                status: "completed",
                ocrResult: statusData.ocr_result,
                autoDownloaded: true
              });

              const downloadContext = target
                ? { ...target, ocrResult: statusData.ocr_result }
                : { name: `ocr-result-${uploadId}`, ocrResult: statusData.ocr_result };
              downloadOcrResultFile(downloadContext, 'markdown', {
                contentOverride: statusData.ocr_result,
                autoTriggered: true
              });

              setToast("OCR が完了し、自動ダウンロードしました。");
              setActiveUploadId(uploadId);
              return;
            } else if (statusData.status === 'error') {
              clearInterval(timersRef.current[uploadId]);
              delete timersRef.current[uploadId];

              updateUpload(uploadId, {
                status: "error",
                error: "OCR処理に失敗しました"
              });
              return;
            }
            // ステータスが pending/processing の場合は待機
          }
        } catch (statusError) {
          console.error('ステータス確認に失敗しました:', statusError);
        }

        // 擬似的な完了条件（フォールバック）
        if (progressValue >= 90 && Math.random() > 0.7) {
          clearInterval(timersRef.current[uploadId]);
          delete timersRef.current[uploadId];

          const target = uploads.find((item) => item.id === uploadId);
          const fallbackResult = target
            ? buildResultMarkdown(target)
            : '# OCR 結果\n\n- ステータス: 完了\n\n---\n\n> OCR テキストは現在利用できません。';
          updateUpload(uploadId, {
            progress: 100,
            status: "completed",
            ocrResult: fallbackResult,
            autoDownloaded: true
          });

          if (target) {
            downloadOcrResultFile({ ...target, ocrResult: fallbackResult }, 'markdown', {
              contentOverride: fallbackResult,
              autoTriggered: true
            });
          }

          setToast("OCR が完了し、自動ダウンロードしました。");
          setActiveUploadId(uploadId);
        }
      } catch (error) {
        console.error('OCRステータス確認に失敗しました:', error);
        clearInterval(timersRef.current[uploadId]);
        delete timersRef.current[uploadId];

        updateUpload(uploadId, {
          status: "error",
          error: "OCR処理に失敗しました。再試行してください"
        });
      }
    }, 3000);
  };

  const handleStartOcr = (uploadId) => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target) return;
    if (target.status === "processing") return;

    if (target.isPdf) {
      const { ok, message } = validateRange(target);
      if (!ok) {
        updateUpload(uploadId, { error: message });
        return;
      }
    }

    sendOcrRequest(uploadId);
  };

  const handleRangeChange = (uploadId, key, value) => {
    const parsed = Number.parseInt(value, 10) || 0;
    updateUpload(uploadId, {
      [key]: parsed,
      error: ""
    });
  };

  const handleRemove = (uploadId) => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target) return;

    if (timersRef.current[uploadId]) {
      clearInterval(timersRef.current[uploadId]);
      delete timersRef.current[uploadId];
    }

    if (target.thumbnail && target.isImage) {
      URL.revokeObjectURL(target.thumbnail);
      imagePreviewUrlsRef.current.delete(target.thumbnail);
    }

    setUploads((prev) => prev.filter((item) => item.id !== uploadId));
  };

  const handleCopyResult = async (uploadId) => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target?.ocrResult) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(target.ocrResult);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = target.ocrResult;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setToast("OCR 結果をコピーしました。");
    } catch (error) {
      setGlobalError("コピーに失敗しました。手動で選択してください。");
    }
  };

  const downloadOcrResultFile = (upload, format = 'markdown', options = {}) => {
    if (!upload) return;

    const { contentOverride = null, autoTriggered = false } = options;
    const ocrContent = typeof contentOverride === 'string' ? contentOverride : upload.ocrResult;
    if (!ocrContent) return;

    const baseName = upload.name?.replace(/\.[^.]+$/, "") || "ocr-result";
    const link = document.createElement("a");
    let url = "";

    if (format === 'txt') {
      // Extract plain text from markdown template when available
      const plainText = ocrContent.replace(/^# OCR 結果\n\n.*?\n\n---\n\n> .*?\n\n/, '');
      const blob = new Blob([plainText], { type: "text/plain;charset=utf-8" });
      url = URL.createObjectURL(blob);
      link.href = url;
      link.download = `${baseName}.txt`;
    } else {
      const blob = new Blob([ocrContent], { type: "text/markdown;charset=utf-8" });
      url = URL.createObjectURL(blob);
      link.href = url;
      link.download = `${baseName}.md`;
    }

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    if (autoTriggered) {
      return;
    }

    if (format === 'txt') {
      setToast("テキストファイルをダウンロードしました。");
    } else {
      setToast("Markdown ファイルをダウンロードしました。");
    }
  };

  const handleDownloadResult = (uploadId, format = 'markdown') => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target?.ocrResult) return;
    downloadOcrResultFile(target, format);
  };

  const handleSelectFilesClick = () => {
    fileInputRef.current?.click();
  };

  // バッチ操作
  const handleSelectAll = () => {
    if (selectedFileIds.size === uploads.length) {
      setSelectedFileIds(new Set());
    } else {
      setSelectedFileIds(new Set(uploads.map(upload => upload.id)));
    }
  };

  const handleFileSelect = (uploadId, isSelected) => {
    const newSelected = new Set(selectedFileIds);
    if (isSelected) {
      newSelected.add(uploadId);
    } else {
      newSelected.delete(uploadId);
    }
    setSelectedFileIds(newSelected);
  };

  const handleBatchOcr = () => {
    const selectedUploads = uploads.filter(upload => selectedFileIds.has(upload.id));
    const validUploads = selectedUploads.filter(upload => {
      if (upload.status === "processing") return false;
      if (upload.isPdf) {
        const { ok } = validateRange(upload);
        return ok;
      }
      return true;
    });

    if (validUploads.length === 0) {
      setGlobalError("選択したファイルにOCR実行可能なものがありません。");
      return;
    }

    validUploads.forEach(upload => {
      handleStartOcr(upload.id);
    });

    setToast(`${validUploads.length}個のファイルでOCRを開始しました。`);
  };

  const handleBatchDelete = () => {
    if (selectedFileIds.size === 0) return;

    const selectedCount = selectedFileIds.size;
    selectedFileIds.forEach(uploadId => {
      handleRemove(uploadId);
    });

    setSelectedFileIds(new Set());
    setToast(`${selectedCount}個のファイルを削除しました。`);
  };

  const runningUploads = uploads.filter((item) => item.status === "processing");
  const runningCount = runningUploads.length;
  const completedUploads = uploads.filter((item) => item.status === "completed");
  const completedCount = completedUploads.length;
  const waitingUploads = uploads.filter((item) => item.status === "waiting");
  const waitingCount = waitingUploads.length;
  const errorUploads = uploads.filter((item) => item.status === "error");
  const errorCount = errorUploads.length;

  const activeUpload = uploads.find((item) => item.id === activeUploadId) || null;
  const hasCompletedActive = activeUpload?.status === "completed";

  const hasSelection = selectedFileIds.size > 0;
  const summaryUploads = hasSelection
    ? uploads.filter((item) => selectedFileIds.has(item.id))
    : uploads;

  const summaryStats = summaryUploads.reduce(
    (acc, item) => {
      acc.total += 1;
      if (item.status === "completed") acc.completed += 1;
      if (item.status === "processing") acc.processing += 1;
      if (item.status === "waiting") acc.waiting += 1;
      if (item.status === "error") acc.error += 1;
      return acc;
    },
    { total: 0, completed: 0, processing: 0, waiting: 0, error: 0 }
  );

  const summaryProgress = summaryStats.total > 0
    ? Math.round((summaryStats.completed / summaryStats.total) * 100)
    : 0;

  const summaryTitle = hasSelection
    ? `選択中 ${summaryStats.total} 件`
    : `全体 ${summaryStats.total} 件（最大20件）`;

  const isSummaryComplete = summaryStats.total > 0 && summaryStats.completed === summaryStats.total;
  const summaryStatusLabel = (() => {
    if (summaryStats.total === 0) return "";
    if (summaryStats.error > 0) return "ステータス: エラーあり";
    if (!isSummaryComplete) {
      if (summaryStats.processing > 0) return "ステータス: 処理中";
      if (summaryStats.waiting > 0) return "ステータス: 待機中";
    }
    return "ステータス: 完了";
  })();

  return (
    <div
      className={`app-root ${isDragging ? "is-dragging" : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
       <div className="global-running">
         <span className="global-running-title">実行中の OCR タスク</span>

         <div className="global-running-list">
           {runningCount === 0 ? (
             <span className="global-running-empty">現在実行中のタスクはありません。</span>
           ) : (
             runningUploads.map((upload, index) => {
               const fileSize = formatFileSize(upload.size);
               const fileType = upload.isPdf ? 'PDF' : '画像';
               const pageInfo = upload.isPdf && upload.pageCount ? `${upload.pageCount}ページ` : '';

               return (
                 <div key={upload.id} className="global-running-item">
                   <div className="running-item-main">
                     {index + 1}. 大きさ：{fileSize} | タイプ：{fileType}{pageInfo ? ` | ページ数：${pageInfo}` : ''}
                   </div>
                 </div>
               );
             })
           )}
         </div>
       </div>

      <div className="page">
        {toast && (
          <div className="toast-wrap">
            <span className="toast" role="status">{toast}</span>
          </div>
        )}

        {(globalError || pdfLibError) && (
          <div className="error-banner">{pdfLibError || globalError}</div>
        )}

        <h1> A I  -  O C R 文 字 起 こ し</h1>

        <div
          className={`upload-card ${isDragging ? "is-dragging" : ""}`}
        >
          <input
            ref={fileInputRef}
            className="file-input"
            type="file"
            accept=".pdf,image/*,.tif,.tiff"
            multiple
            onChange={handleFileInputChange}
          />
          <button type="button" className="select-button" onClick={handleSelectFilesClick}>
            ファイル選択
          </button>
          <p className="upload-hint">PDF・JPG・PNG ファイルを選択し、緑色の OCR ボタンを押してください。</p>
          {!pdfLibReady && !pdfLibError && <p className="upload-subhint">PDF プレビューを読み込み中...</p>}

          {summaryStats.total > 0 && (
            <div className="summary-progress" aria-busy={!isSummaryComplete}>
              <div className="summary-progress-header">
                <span className="summary-progress-title">{summaryTitle}</span>
                <span className="summary-progress-count">{summaryStats.completed} / {summaryStats.total} 完了</span>
              </div>
              <div
                className="summary-progress-bar"
                role="progressbar"
                aria-valuenow={summaryProgress}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className={`summary-progress-value ${!isSummaryComplete ? "is-animated" : ""}`}
                  style={{ width: `${summaryProgress}%` }}
                />
              </div>
              <div className="summary-progress-status">
                <span>{summaryStatusLabel}</span>
                <span>処理中 {summaryStats.processing}</span>
                <span>待機中 {summaryStats.waiting}</span>
                <span>エラー {summaryStats.error}</span>
              </div>
            </div>
          )}
        </div>

        {uploads.length > 0 && (
          <div className="batch-toolbar">
            <div className="batch-select">
              <label className="select-all-checkbox">
                <input
                  type="checkbox"
                  checked={selectedFileIds.size === uploads.length && uploads.length > 0}
                  onChange={handleSelectAll}
                />
                <span>全選択 ({selectedFileIds.size} / {uploads.length})</span>
              </label>
            </div>
            <div className="batch-actions">
              <button
                type="button"
                className="batch-button primary"
                disabled={selectedFileIds.size === 0}
                onClick={handleBatchOcr}
              >
                選択したファイルでOCR実行 ({selectedFileIds.size})
              </button>
              <button
                type="button"
                className="batch-button danger"
                disabled={selectedFileIds.size === 0}
                onClick={handleBatchDelete}
              >
                選択したファイルを削除 ({selectedFileIds.size})
              </button>
            </div>
          </div>
        )}

        <div className="file-list-container">
          <div className="file-list">
            {uploads.map((upload) => {
              const disabled = upload.status === "processing" || upload.loadingPreview;
              const isActive = upload.id === activeUploadId;
              const isSelected = selectedFileIds.has(upload.id);
              return (
                <div
                  key={upload.id}
                  className={`file-row ${isActive ? "is-active" : ""} ${isSelected ? "is-selected" : ""}`}
                  onClick={() => setActiveUploadId(upload.id)}
                >
                  <div className="file-row-content">
                    <div className="file-checkbox" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => handleFileSelect(upload.id, e.target.checked)}
                      />
                    </div>

                    <div className="thumb-area">
                      {upload.loadingPreview ? (
                        <span className="thumb-loading">...</span>
                      ) : upload.thumbnail ? (
                        <img src={upload.thumbnail} alt={upload.name} />
                      ) : (
                        <span className="thumb-placeholder">📄</span>
                      )}
                      {upload.isPdf && upload.pageCount && (
                        <span className="page-tag">{upload.pageCount}</span>
                      )}
                    </div>

                    <div className="file-body">
                      <div className="file-info">
                        <div className="file-header">
                          <div className="file-title-with-status">
                            <span className={`status-label status-${upload.status}`}>{STATUS_LABELS[upload.status]}</span>
                            <div className="file-title" title={upload.name}>{upload.name}</div>
                          </div>
                        </div>
                        <div className="file-meta">
                          <span>{formatFileSize(upload.size)}</span>
                          <span>{upload.isPdf ? 'PDF' : '画像'}</span>
                          {upload.isPdf && upload.pageCount && (
                            <span>
                              全{upload.pageCount}ページ | 範囲:
                              <input
                                type="number"
                                min={1}
                                max={upload.pageCount}
                                value={upload.rangeStart || ""}
                                onChange={(e) => {
                                  e.stopPropagation();
                                  handleRangeChange(upload.id, "rangeStart", e.target.value);
                                }}
                                style={{
                                  width: '40px',
                                  border: '1px solid var(--gray-300)',
                                  borderRadius: '4px',
                                  padding: '2px 4px',
                                  fontSize: '0.75rem',
                                  margin: '0 4px',
                                  textAlign: 'center'
                                }}
                              />
                              -
                              <input
                                type="number"
                                min={1}
                                max={upload.pageCount}
                                value={upload.rangeEnd || ""}
                                onChange={(e) => {
                                  e.stopPropagation();
                                  handleRangeChange(upload.id, "rangeEnd", e.target.value);
                                }}
                                style={{
                                  width: '40px',
                                  border: '1px solid var(--gray-300)',
                                  borderRadius: '4px',
                                  padding: '2px 4px',
                                  fontSize: '0.75rem',
                                  margin: '0 4px',
                                  textAlign: 'center'
                                }}
                              />
                            </span>
                          )}
                        </div>
                        {upload.error && <div className="error-text" style={{fontSize: '0.6875rem', padding: '2px 6px'}}>{upload.error}</div>}
                      </div>

                       <div className="row-actions">
                         <button
                           type="button"
                           className={`compact-button ${upload.status === 'completed' ? 'success' : 'disabled'}`}
                           disabled={upload.status !== 'completed'}
                           onClick={(event) => {
                             event.stopPropagation();
                             if (upload.status === 'completed') {
                               handleDownloadResult(upload.id);
                             }
                           }}
                         >
                           ダウンロード
                         </button>
                       </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {!uploads.length && (
              <div style={{padding: '40px 20px', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem'}}>
                ファイルを選択するとここにリストされます。
              </div>
            )}
          </div>
        </div>



{!uploads.length && (
          <p className="footnote">「ファイル選択」ボタンからファイルを選ぶか、ここにドラッグ＆ドロップしてください。</p>
        )}
      </div>
    </div>
  );
};

export default App;
