import React, { useState, useRef, useEffect } from "react";
import "./App.css";
import { FaUser } from 'react-icons/fa';

const SERVER_ADDRESS = process.env.REACT_APP_SERVER_ADDRESS;
const NGINX_PORT = process.env.REACT_APP_NGINX_PORT;
const API_BASE_URL = `https://${SERVER_ADDRESS}:${NGINX_PORT}`;

const App = () => {
  const [fileNames, setFileNames] = useState([]);
  const [totalDuration, setTotalDuration] = useState(0);
  const [status, setStatus] = useState("「ファイル選択」をクリックして音声ファイルを選び、「翻訳」をクリックしてください。");
  //const [estimatedTime, setEstimatedTime] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [audioIds, setAudioIds] = useState({});
  const [username, setUsername] = useState("");
  const [isResultsOpen, setIsResultsOpen] = useState(false);
  const [language, setLanguage] = useState("Japanese");
  const fileInputRef = useRef(null);
  const pollInterval = 1000;
  const [pendingCount, setPendingCount] = useState(0);
  const [serverStatusColor, setServerStatusColor] = useState('green');
  const [translationResults, setTranslationResults] = useState([]);
  const [uniqueFileNames, setUniqueFileNames] = useState([]);
  const [isPopupVisible, setIsPopupVisible] = useState(false);
  const [estimatedCompletionTime, setEstimatedCompletionTime] = useState("");
  const [format, setFormat] = useState("txt"); // 新增状态：输出格式选择
  const [filter, setFilter] = useState({
    fileName: '',
    status: '',
    language: '',
    format: '',
  });
  const [uploadedFilesCount, setUploadedFilesCount] = useState(0);

  // useEffect(() => {
  //   if (uploadedFilesCount === fileNames.length && fileNames.length > 0) {
  //     setIsPopupVisible(true); // 显示弹出窗口
  //   }
  // }, [uploadedFilesCount, fileNames.length]);

  useEffect(() => {
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }

    const urlParams = new URLSearchParams(window.location.search);
    const usernameFromURL = urlParams.get('username');
    if (usernameFromURL) {
      setUsername(usernameFromURL);
    }
  }, []);

  const handleLogout = () => {
    fetch(`${API_BASE_URL}/logout`, {
      method: 'GET',
      credentials: 'include',
    })
    .then(response => {
      if (response.ok) {
        localStorage.clear();
        sessionStorage.clear();
        window.location.href = "https://192.168.10.9:33380/";
      }
    })
    .catch(error => {
      console.error('Logout failed:', error);
    });
  };

  const handleFileChange = (event) => {
    const files = Array.from(event.target.files);
    updateFileList(files);
  };

  const toggleResults = () => {
    setIsResultsOpen(!isResultsOpen);
    if (!isResultsOpen) {
      fetchTranslationResults();
    }
  };

  const handleLanguageChange = (event) => {
    setLanguage(event.target.value);
  };

  const updateFileList = async (files) => {
    const newFileNames = files.map(file => file.name);
    setFileNames(newFileNames);
    const newTotalDuration = await recalculateTotalDuration(files);
    setTotalDuration(newTotalDuration);
    //updateEstimatedTime(newTotalDuration);
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

  // const updateEstimatedTime = (duration) => {
  //   const estimatedProcessingTime = duration / 10;
  //   const completionTime = new Date(Date.now() + estimatedProcessingTime * 1000);
  //   const hours = completionTime.getHours().toString().padStart(2, "0");
  //   const minutes = completionTime.getMinutes().toString().padStart(2, "0");
  //   setEstimatedTime(`目安完了時間  ${hours}:${minutes}`);
  // };

  const handleConfirmClick = async () => {
    if (fileNames.length === 0) {
      return alert("音声ファイルを選択してください。");
    }

    setStatus("翻訳中...");
    setIsTranslating(true);
    clearDownloadLinks();
    setUploadedFilesCount(0); // 重置计数
    setIsPopupVisible(false); // 重置弹窗可见性

    try {
      const newAudioIds = {};
      for (const fileName of fileNames) {
        const file = Array.from(fileInputRef.current.files).find(file => file.name === fileName);
        if (file) {
          const audioId = await translateFile(file);
          newAudioIds[fileName] = audioId;
          setUploadedFilesCount(prevCount => prevCount + 1);
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

  // Function to fetch the estimated completion time
  const fetchEstimatedCompletionTime = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/estimated_completion_time`);
      console.log("API Response:", response);
      if (response.ok) {
        const data = await response.json();
        console.log("Estimated Time Data:", data);
        setEstimatedCompletionTime(data.estimated_time); // Update the state with the returned value
        setIsPopupVisible(true); // Show the popup after fetching the time
      } else {
        console.error("Failed to fetch estimated completion time");
      }
    } catch (error) {
      console.error("Error fetching estimated completion time:", error);
    }
  };


  // useEffect to trigger the API call and show the popup
  useEffect(() => {
    if (uploadedFilesCount === fileNames.length && fileNames.length > 0) {
      fetchEstimatedCompletionTime();
    }
  }, [uploadedFilesCount, fileNames.length]);

  const fetchTranslationResults = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/translation_results?username=${username}`);
      const data = await response.json();
      setTranslationResults(data.results || []);

      const uniqueFiles = [...new Set(data.results.map(result => result.file_name))];
      setUniqueFileNames(uniqueFiles);
    } catch (error) {
      console.error("Error fetching translation results:", error);
    }
  };

  const fetchPendingCount = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/pending_count`);
      const data = await response.json();
      setPendingCount(data.count);

      if (data.count < 20) {
        setServerStatusColor('green');
      } else if (data.count < 40) {
        setServerStatusColor('yellow');
      } else {
        setServerStatusColor('red');
      }
    } catch (error) {
      console.error("Error fetching pending count:", error);
    }
  };

  useEffect(() => {
    fetchPendingCount();
    const interval = setInterval(fetchPendingCount, 5000);
    return () => clearInterval(interval);
  }, []);

  const translateFile = async (file) => {
    const formData = new FormData();
    const audioDuration = await getAudioDuration(file);
    const audioType = file.type;
    formData.append("audio_file", file);
    formData.append("language", language);
    formData.append("username", username);
    formData.append("duration", audioDuration);
    formData.append("file_type", audioType);
    formData.append("format", format);

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
              audioIds[fileName] = null;
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
    downloadLink.download = fileName.replace(/\.[^/.]+$/, "") + `.${format}`;

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
    //updateEstimatedTime(newTotalDuration);
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
      <h1>音 声 ファイル 文 字 起 こ し</h1>
      <div className="header">
      <select className="format-select" value={format} onChange={(e) => setFormat(e.target.value)}>
          <option value="txt">txt</option>
          {/* <option value="docx">docx</option> */}
          <option value="md">md</option>
          <option value="rtf">rtf</option>
        </select>
        <select className="language-select" value={language} onChange={handleLanguageChange}>
          <option value="Japanese">Japanese</option>
          <option value="English">English</option>
          <option value="Chinese">Chinese</option>
        </select>
        <button onClick={toggleResults} className="results-button">翻訳結果</button>
        {username && (
          <>
            <div className="user-icon">
              <FaUser />
              <span className="username">{username}</span>
            </div>
            <button onClick={handleLogout} className="logout-button">Logout</button>
          </>
        )}
      </div>

      {isResultsOpen && (
        <div className="modal">
          <div className="modal-content">
            <span className="close" onClick={toggleResults}>&times;</span>
            <h2>翻訳結果</h2>
            {/* 筛选器 */}
            <div className="filters">
              <select
                value={filter.fileName}
                onChange={(e) => setFilter({ ...filter, fileName: e.target.value })}
              >
                <option value="">全てのファイル</option>
                {uniqueFileNames.map((fileName, index) => (
                  <option key={index} value={fileName}>{fileName}</option>
                ))}
              </select>
              <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
                <option value="">全ての状態</option>
                <option value="pending">Pending</option>
                <option value="processing">Processing</option>
                <option value="completed">Completed</option>
                <option value="canceled">Canceled</option>
              </select>
              <select value={filter.language} onChange={(e) => setFilter({ ...filter, language: e.target.value })}>
                <option value="">全ての言語</option>
                <option value="Japanese">Japanese</option>
                <option value="English">English</option>
                <option value="Chinese">Chinese</option>
              </select>
              <select value={filter.format} onChange={(e) => setFilter({ ...filter, format: e.target.value })}> {/* 新增的格式过滤器 */}
                <option value="">全てのフォーマット</option>
                <option value="txt">txt</option>
                {/* <option value="docx">docx</option> */}
                <option value="md">md</option>
                <option value="rtf">rtf</option>
              </select>
            </div>
            {translationResults.length > 0 ? (
              <div className="table-container">
                <table>
                  <thead>
                  <tr>
                    <th>ユーザー名</th>
                    <th>ファイル名</th>
                    <th>翻訳結果DL</th>
                    <th>フォーマット</th>
                    <th>長さ【単位：秒】</th>
                    <th>タイプ</th>
                    <th>実行状態</th>
                    <th>翻訳言語</th>
                    <th>アップロード時間</th>
                  </tr>
                </thead>
                <tbody>
                {translationResults
                  .sort((a, b) => new Date(a.upload_time) - new Date(b.upload_time))
                  .filter((result) => {
                    return (
                      (filter.fileName === '' || result.file_name === filter.fileName) &&
                      (filter.status === '' || result.status === filter.status) &&
                      (filter.language === '' || result.translation_language === filter.language) &&
                      (filter.format === '' || result.format === filter.format)
                    );
                  })
                  .map((result, index) => (
                    <tr key={index}>
                      <td>{result.user_name}</td>
                      <td>{result.file_name}</td>
                      <td>
                        {result.result_url ? (
                          <a href={result.result_url} target="_blank" rel="noopener noreferrer">リンク</a>
                        ) : (
                          "N/A"
                        )}
                      </td>
                      <td>{result.format}</td>
                      <td>{result.audio_length}</td>
                      <td>{result.file_type}</td>
                      <td>{result.status}</td>
                      <td>{result.translation_language}</td>
                      <td>{result.upload_time}</td>
                    </tr>
                  ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>翻訳結果はありません。</p>
            )}
          </div>
        </div>
      )}

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
              className={`delete-button ${isTranslating ? 'disabled' : ''}`}
              onClick={() => deleteFile(fileName)}
              disabled={isTranslating} // 禁用删除按钮
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
      {/* <div id="estimatedTime" className="estimated-time" style={{ marginTop: 10 }}>
        {estimatedTime}
      </div> */}
      <div id="status" className="status">
        {status}
      </div>
      <div className="server-status">
        サーバー状態  :
        <span
          className="server-status-dot"
          style={{ backgroundColor: serverStatusColor }}
        ></span>
        <div className="pending-count">
          未処理数 : {pendingCount}個
        </div>
      </div>
      {isPopupVisible && (
        <div className="popup">
          <div className="popup-content">
            <span className="close" onClick={() => setIsPopupVisible(false)}>&times;</span>
            <p>すべてのファイルをアップロード済。</p>
            <p>ブラウザを閉じても構いません。</p>
            <p>目安完了時間 <span style={{ color: 'red' }}>{estimatedCompletionTime}</span> 以降に。</p>
            <p>再ログインし結果を確認してください。</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
