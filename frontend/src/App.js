import React, { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

const SUPPORTED_EXTENSIONS = ["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"];
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

    let rejected = 0;
    const newUploads = [];

    files.forEach((file, index) => {
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

    if (rejected) {
      setGlobalError(`サポートされていないファイルを ${rejected} 件スキップしました。`);
    } else {
      setGlobalError("");
    }

    if (newUploads.length) {
      setUploads((prev) => [...newUploads, ...prev]);
      setActiveUploadId(newUploads[0].id);
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
      error: ""
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

      // 开始轮询检查OCR状态
      pollOcrStatus(uploadId, result.task_id || uploadId);

    } catch (error) {
      console.error('OCR请求失败:', error);
      updateUpload(uploadId, {
        status: "error",
        error: error.message || "OCR请求失败，请重试"
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
        // 模拟进度增长
        progressValue = Math.min(progressValue + Math.floor(Math.random() * 15) + 5, 95);

        updateUpload(uploadId, { progress: progressValue });

        // 实际的状态查询API调用
        try {
          const statusResponse = await fetch(`/api/aibt/ocr/status/${taskId}`);
          if (statusResponse.ok) {
            const statusData = await statusResponse.json();

            // 根据实际状态更新进度
            if (statusData.status === 'completed' && statusData.ocr_result) {
              clearInterval(timersRef.current[uploadId]);
              delete timersRef.current[uploadId];

              updateUpload(uploadId, {
                progress: 100,
                status: "completed",
                ocrResult: statusData.ocr_result
              });

              setToast("OCR が完了しました。結果を確認してください。");
              setActiveUploadId(uploadId);
              return;
            } else if (statusData.status === 'error') {
              clearInterval(timersRef.current[uploadId]);
              delete timersRef.current[uploadId];

              updateUpload(uploadId, {
                status: "error",
                error: "OCR处理失败"
              });
              return;
            }
            // 如果状态是pending或processing，继续等待
          }
        } catch (statusError) {
          console.error('状态查询失败:', statusError);
        }

        // 模拟完成条件（作为后备方案）
        if (progressValue >= 90 && Math.random() > 0.7) {
          clearInterval(timersRef.current[uploadId]);
          delete timersRef.current[uploadId];

          const target = uploads.find((item) => item.id === uploadId);
          updateUpload(uploadId, {
            progress: 100,
            status: "completed",
            ocrResult: buildResultMarkdown(target)
          });

          setToast("OCR が完了しました。結果を確認してください。");
          setActiveUploadId(uploadId);
        }
      } catch (error) {
        console.error('OCR状态查询失败:', error);
        clearInterval(timersRef.current[uploadId]);
        delete timersRef.current[uploadId];

        updateUpload(uploadId, {
          status: "error",
          error: "OCR处理失败，请重试"
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

  const handleDownloadResult = (uploadId, format = 'markdown') => {
    const target = uploads.find((item) => item.id === uploadId);
    if (!target?.ocrResult) return;

    const baseName = target.name?.replace(/\.[^.]+$/, "") || "ocr-result";

    if (format === 'txt') {
      // Extract plain text from markdown
      const plainText = target.ocrResult.replace(/^# OCR 結果\n\n.*?\n\n---\n\n> .*?\n\n/, '');
      const blob = new Blob([plainText], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${baseName}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setToast("テキストファイルをダウンロードしました。");
    } else {
      const blob = new Blob([target.ocrResult], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${baseName}.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setToast("Markdown ファイルをダウンロードしました。");
    }
  };

  const handleSelectFilesClick = () => {
    fileInputRef.current?.click();
  };

  const runningUploads = uploads.filter((item) => item.status === "processing");
  const runningCount = runningUploads.length;
  const activeUpload = uploads.find((item) => item.id === activeUploadId) || null;
  const hasCompletedActive = activeUpload?.status === "completed";

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
          <p className="upload-hint">PDF と画像（JPG / PNG）に対応しています。</p>
          {!pdfLibReady && !pdfLibError && <p className="upload-subhint">PDF プレビューを読み込み中...</p>}
        </div>

        <div className="file-list">
          {uploads.map((upload) => {
            const disabled = upload.status === "processing" || upload.loadingPreview;
            const isActive = upload.id === activeUploadId;
            return (
              <div
                key={upload.id}
                className={`file-row ${isActive ? "is-active" : ""}`}
                onClick={() => setActiveUploadId(upload.id)}
              >
                <div className="thumb-area">
                  {upload.loadingPreview ? (
                    <span className="thumb-loading">生成中...</span>
                  ) : upload.thumbnail ? (
                    <img src={upload.thumbnail} alt={upload.name} />
                  ) : (
                    <span className="thumb-placeholder">プレビューなし</span>
                  )}
                  {upload.isPdf && upload.pageCount && (
                    <span className="page-tag">{upload.pageCount} ページ</span>
                  )}
                </div>

                <div className="file-body">
                  <div className="file-header">
                    <div className="file-title" title={upload.name}>{upload.name}</div>
                    <span className={`status-chip status-${upload.status}`}>{STATUS_LABELS[upload.status]}</span>
                  </div>
                  <div className="file-meta">
                    <span>{formatFileSize(upload.size)}</span>
                    {!upload.isPdf && <span>画像</span>}
                    {upload.isPdf && upload.pageCount && <span>PDF</span>}
                  </div>

                  {upload.isPdf && (
                    <>
                      <div className="range-label">OCR するページ範囲を指定できます</div>
                      <div className="range-row">
                        <label>
                          開始ページ
                          <input
                            type="number"
                            min={1}
                            max={upload.pageCount || undefined}
                            value={upload.rangeStart || ""}
                            onChange={(event) => handleRangeChange(upload.id, "rangeStart", event.target.value)}
                          />
                        </label>
                        <label>
                          終了ページ
                          <input
                            type="number"
                            min={1}
                            max={upload.pageCount || undefined}
                            value={upload.rangeEnd || ""}
                            onChange={(event) => handleRangeChange(upload.id, "rangeEnd", event.target.value)}
                          />
                        </label>
                        <span className="range-hint">(全 {upload.pageCount || "-"} ページ)</span>
                      </div>
                    </>
                  )}

                  <div className={`progress-row ${upload.status === "processing" ? "is-processing" : ""}`}>
                    <div className="progress-bar">
                      <div
                        className={`progress-value ${upload.status === "processing" ? "is-animated" : ""}`}
                        style={upload.status === "processing" ? undefined : { width: `${upload.progress}%` }}
                      />
                    </div>
                  </div>

                  {upload.error && <div className="error-text">{upload.error}</div>}

                  <div className="row-actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={disabled}
                      onClick={(event) => {
                        event.stopPropagation();
                        handleStartOcr(upload.id);
                      }}
                    >
                      OCR 実行
                    </button>
                    <button
                      type="button"
                      className="danger"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleRemove(upload.id);
                      }}
                    >
                      削除
                    </button>
                  </div>
                </div>
              </div>
            );
          })}

          {!uploads.length && (
            <p className="empty-message">ファイルを選択するとここにリストされます。</p>
          )}
        </div>

        {hasCompletedActive && (
          <section className="result-panel">
            <div className="result-header">
              <h2>OCR 結果</h2>
              <div className="result-actions">
                <button type="button" onClick={() => handleCopyResult(activeUpload.id)}>コピー</button>
                <button type="button" onClick={() => handleDownloadResult(activeUpload.id, 'txt')}>TXT 保存</button>
                <button type="button" onClick={() => handleDownloadResult(activeUpload.id)}>Markdown 保存</button>
              </div>
            </div>
            <div className="result-body">
              <pre className="result-text">{activeUpload.ocrResult}</pre>
            </div>
          </section>
        )}

{!uploads.length && (
          <p className="footnote">「ファイル選択」ボタンからファイルを選ぶか、ここにドラッグ＆ドロップしてください。</p>
        )}
      </div>
    </div>
  );
};

export default App;
