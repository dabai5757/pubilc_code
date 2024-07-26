import React, { useState, useRef, useEffect } from "react";
import "./App.css";

const SERVER_ADDRESS = process.env.REACT_APP_SERVER_ADDRESS;
const NGINX_PORT = process.env.REACT_APP_NGINX_PORT;
const API_BASE_URL = `https://${SERVER_ADDRESS}:${NGINX_PORT}`;

const App = () => {
  const [fileNames, setFileNames] = useState([]);
  const [totalDuration, setTotalDuration] = useState(0);
  const [status, setStatus] = useState("「ファイル選択」をクリックして音声ファイルを選び、「翻訳」をクリックしてください。");
  const [estimatedTime, setEstimatedTime] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [audioIds, setAudioIds] = useState({});
  const fileInputRef = useRef(null);
  const pollInterval = 1000;

  useEffect(() => {
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files);
    updateFileList(files);
  };

  const updateFileList = async (files) => {
    const newFileNames = files.map(file => file.name);
    setFileNames(newFileNames);
    const newTotalDuration = await recalculateTotalDuration(files);
    setTotalDuration(newTotalDuration);
    updateEstimatedTime(newTotalDuration);
  };

  const recalculateTotalDuration = async (files) => {
    let newTotalDuration = 0;
    for (const file of files) {
      const duration = await getAudioDuration(file);
      newTotalDuration += duration;
    }
    return newTotalDuration;
  };

  const getAudioDuration = (file) => {
    return new Promise((resolve) => {
      const audio = document.createElement("audio");
      audio.src = URL.createObjectURL(file);
      audio.addEventListener("loadedmetadata", () => {
        resolve(audio.duration);
        URL.revokeObjectURL(audio.src);
      });
    });
  };

  const updateEstimatedTime = (duration) => {
    const estimatedProcessingTime = duration / 10;
    const completionTime = new Date(Date.now() + estimatedProcessingTime * 1000);

    const hours = completionTime.getHours().toString().padStart(2, "0");
    const minutes = completionTime.getMinutes().toString().padStart(2, "0");

    setEstimatedTime(`目安完了時間: ${hours}:${minutes}`);
  };

  const handleConfirmClick = async () => {
    if (fileNames.length === 0) {
      return alert("音声ファイルを選択してください。");
    }

    setStatus("翻訳中...");
    setIsTranslating(true);

    clearDownloadLinks();

    try {
      const newAudioIds = {};
      for (const fileName of fileNames) {
        const file = Array.from(fileInputRef.current.files).find(file => file.name === fileName);
        if (file) {
          const audioId = await translateFile(file);
          newAudioIds[fileName] = audioId;
        }
      }
      setAudioIds(newAudioIds);
      pollForResults(newAudioIds);
    } catch (error) {
      console.error("Fetch 操作中にエラーが発生しました:", error.message);
      setStatus(error.name === "AbortError" ? "リクエストのタイムアウト" : "翻訳エラー");
      setIsTranslating(false);
    }
  };

  const translateFile = async (file) => {
    const formData = new FormData();
    formData.append("audio_file", file);

    const options = {
      method: "POST",
      body: formData,
    };

    const response = await fetch(`${API_BASE_URL}/api/aibt/transcribe`, options);

    if (!response.ok) {
      throw new Error("ネットワーク応答が正しくありませんでした");
    }

    const data = await response.json();
    return data.audio_file_id;
  };

  const pollForResults = (audioIds) => {
    const interval = setInterval(async () => {
      let allCompleted = true;
      for (const [fileName, audioId] of Object.entries(audioIds)) {
        if (audioId) {
          try {
            const response = await fetch(`${API_BASE_URL}/api/aibt/get_url`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({ audio_id: audioId }),
            });

            if (!response.ok) {
              throw new Error(`HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            if (data.result_url !== null) {
              createDownloadLink(data.result_url, fileName);
              audioIds[fileName] = null;  // Mark as completed
            } else {
              allCompleted = false;
            }
          } catch (error) {
            console.error("Error polling for results:", error);
            allCompleted = false;
          }
        }
      }
      if (allCompleted) {
        clearInterval(interval);
        setStatus("翻訳完了");
        setIsTranslating(false);
        showNotification("翻訳が完了しました！");
      }
    }, pollInterval);
  };

  const showNotification = (title, body) => {
    if (Notification.permission === "granted") {
      new Notification(title, { body });
    }
  };

  const clearDownloadLinks = () => {
    const downloadLinks = document.querySelectorAll(".download-link");
    downloadLinks.forEach((link) => {
      link.remove();
    });
  };

  const createDownloadLink = (transcriptionUrl, fileName) => {
    const escapedFileName = CSS.escape(fileName);
    const existingDownloadLink = document.querySelector(`#${escapedFileName}-download-link`);
    if (existingDownloadLink) {
      existingDownloadLink.remove();
    }

    const downloadLink = document.createElement("a");
    downloadLink.href = transcriptionUrl;
    downloadLink.textContent = "ダウンロード";
    downloadLink.classList.add("download-link");
    downloadLink.id = `${escapedFileName}-download-link`;
    downloadLink.style.marginLeft = "10px";
    downloadLink.download = fileName.replace(/\.[^/.]+$/, "") + ".txt";

    const fileListItem = document.querySelector(`#file-item-${fileNames.indexOf(fileName)}`);
    if (fileListItem) {
      const fileNameSpan = fileListItem.querySelector(".file-name-span");
      fileListItem.insertBefore(downloadLink, fileNameSpan.nextSibling);
    }
  };

  const deleteFile = async (fileName) => {
    const updatedFileNames = fileNames.filter(name => name !== fileName);
    setFileNames(updatedFileNames);
    const updatedFiles = updateFileInput(updatedFileNames);
    const newTotalDuration = await recalculateTotalDuration(updatedFiles);
    setTotalDuration(newTotalDuration);
    updateEstimatedTime(newTotalDuration);
  };

  const updateFileInput = (updatedFileNames) => {
    const dataTransfer = new DataTransfer();
    const updatedFiles = [];
    updatedFileNames.forEach(name => {
      const file = Array.from(fileInputRef.current.files).find(file => file.name === name);
      if (file) {
        dataTransfer.items.add(file);
        updatedFiles.push(file);
      }
    });
    fileInputRef.current.files = dataTransfer.files;
    return updatedFiles;
  };

  useEffect(() => {
    const progressBar = document.getElementById("progressBar");
    if (progressBar) {
      progressBar.style.animationPlayState = isTranslating ? "running" : "paused";
    }
  }, [isTranslating]);

  return (
    <div className="container">
      <h1>音声ファイルの文字起こし</h1>
      <div className="file-path-container">
        <label htmlFor="fileInput" id="browseButton" className="file-input-label">
          ファイル選択
        </label>
        <input
          type="file"
          id="fileInput"
          accept=".wav, .mp3"
          multiple
          style={{ display: "none" }}
          onChange={handleFileChange}
          ref={fileInputRef}
        />
      </div>
      <div id="fileListContainer">
        <ul id="fileList">
          {fileNames.map((fileName, index) => (
            <li key={fileName} id={`file-item-${index}`} className="file-list-item">
              <span className="file-name-span">{fileName}</span>
              <span className="file-duration-span"></span>
              <button
                className="delete-button"
                onClick={() => deleteFile(fileName)}
              >
                削除
              </button>
            </li>
          ))}
        </ul>
      </div>
      <button
        id="confirmButton"
        className="custom-button"
        disabled={isTranslating}
        onClick={handleConfirmClick}
      >
        翻訳
      </button>
      <div id="progressBarContainer" className="progress-bar-container">
        <div id="progressBar" className="progress-bar" style={{ display: isTranslating ? "block" : "none" }}></div>
      </div>
      <div id="estimatedTime" className="estimated-time" style={{ marginTop: 10 }}>
        {estimatedTime}
      </div>
      <div id="status" className="status">
        {status}
      </div>
    </div>
  );
};

export default App;
