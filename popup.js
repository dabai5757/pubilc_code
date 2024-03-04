// chrome-rec/popup.js
function popup_run() {
  // DOM 関連の変数
  var recordButton = document.getElementById('recordButton');
  var resultsDiv = document.getElementById('results');
  // script 関連の変数
  var isRecording = false;
  var mediaRecorder;
  var streams = [];
  var audioChunks = [];
  var audioContext = null;
  var mediaStreamSourceMic = null;
  var mediaStreamSourceSpeaker = null
  var merger = null;
  var mediaStreamDestination = null;
  var analyserMic = null;
  var analyserSpeaker = null;

  recordButton.addEventListener('click', function(event) {
    event.preventDefault();
    if (!mediaRecorder || mediaRecorder.state === 'inactive') {
      // 録音スタート
      startRecording();
    } else {
      // ユーザが停止を選択したら録音終了
      finishRecording();
    }
  });

  window.addEventListener('beforeunload', function (e) {
    if (isRecording) {
      const confirmationMessage = '録音を保存しないで終了しますか？';
      e.returnValue = confirmationMessage;  // これにより、確認ダイアログが表示されます
      return confirmationMessage;  // 一部の古いブラウザーで必要です
    }
  });

  const startRecording = async function() {
    isRecording = true;
    audioChunks = [];

    if(streams.length === 0) {
      // 入力中でない場合
      try {
        // ユーザのマイクをキャプチャ
        streams[0] = await navigator.mediaDevices.getUserMedia({ audio: true });
        // バックグラウンドスクリプトにデスクトップオーディオをキャプチャするように指示
        chrome.runtime.sendMessage({action: 'capture_audio'}, (response) => {
          if (response && response.cancelled) {
            // 起動中止なら finalyze する
            finishRecording();
          }
        });
        chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
          if (msg.streamId) {
            navigator.mediaDevices.getUserMedia({
              audio:{
                mandatory: {
                  chromeMediaSource: 'desktop',
                  chromeMediaSourceId: msg.streamId
                }
              },
              video: {
                mandatory: {
                  chromeMediaSource: 'desktop',
                  chromeMediaSourceId: msg.streamId
                }
              }
            }).then(stream => {
              const audioTracks = stream.getAudioTracks();
              if (audioTracks.length === 0) {
                // 音声トラックが存在しない場合はalertを出す
                alert("システムの音声を共有するをONにしてください。");
                sendResponse({success: false, error: "システムの音声を共有するをONにしてください。"});  // エラーを示す
                finishRecording();
                return
              }
              stream.getVideoTracks().forEach(track => stream.removeTrack(track)); // videoトラック削除
              streams[1] = stream;
              console.log("streams:", streams);
              streams.forEach(stream => { console.log("streams.getTracks():", stream.getTracks()); });
              // streams から mediaStreamSource を準備
              var audioContext = new (window.AudioContext || window.webkitAudioContext)();
              var mediaStreamSourceMic = audioContext.createMediaStreamSource(streams[0]);
              var mediaStreamSourceSpeaker = audioContext.createMediaStreamSource(streams[1]);
              var mediaStreamDestination = audioContext.createMediaStreamDestination();
              // ChannelMerger を準備
              var merger = audioContext.createChannelMerger(2);
              // 音量解析ため analyser を準備
              analyserMic = audioContext.createAnalyser();
              analyserSpeaker = audioContext.createAnalyser();
              // 音量を調節するための gainNode を準備(増やすと小さい音を拾いやすくなる一方、大きい音は一定上限に正規化されるので、かえって聞こえにくい？)
              var gainNodeMic = audioContext.createGain();
              gainNodeMic.gain.value = 1.0;
              var gainNodeSpeaker = audioContext.createGain();
              gainNodeSpeaker.gain.value = 1.0;
              var gainNodeDest = audioContext.createGain();
              gainNodeDest.gain.value = 1.0;

              // mediaStreamSource を gainNode に接続
              mediaStreamSourceMic.connect(gainNodeMic);
              mediaStreamSourceSpeaker.connect(gainNodeSpeaker);
              // mediaStreamSource を analyser に接続
              analyserMic.fftSize = 256;
              analyserSpeaker.fftSize = 256;
              mediaStreamSourceMic.connect(analyserMic);
              mediaStreamSourceSpeaker.connect(analyserSpeaker);
              // gainNode を merger に接続
              gainNodeMic.connect(merger, 0, 0);  // マイク音声は左チャネル
              gainNodeSpeaker.connect(merger, 0, 1);  // スピーカー音声は右チャネル
              // merger を gainNodeDest に接続
              merger.connect(gainNodeDest);
              // gainNodeDest を MediaStreamDestination に接続
              gainNodeDest.connect(mediaStreamDestination);

              // MediaRecorder(WebAPI版) を作成
              // MediaRecorderは'audio/wav'や'audio/mpeg'(mp3)をsupportしていないので、webm を利用する。
              // MediaRecorderをnewしなおさないとwebmヘッダーが付加されない
              if (mediaStreamDestination.stream instanceof MediaStream) {
                mediaRecorder = new MediaRecorder(mediaStreamDestination.stream, {mimeType: 'audio/webm;codecs=opus', bitsPerSecond: 128000}); // bitrate を指定
                mediaRecorder.addEventListener('dataavailable', onDataAvailable);
                mediaRecorder.addEventListener('stop', onStop);
                try{
                  mediaRecorder.start();
                } catch (error) {
                  if (error.name === 'NotSupportedError') {
                    alert('エラー: MediaRecorderは開始できません。利用可能なオーディオまたはビデオトラックがありません。\n解決策: 「画面全体の共有」画面で、「システムの音声も共有する」を選択すると解決することがあります。');
                  }
                }
                recordButton.textContent = '音声録音終了';
              } else {
                console.log('Failed to construct MediaRecorder: stream is not of type MediaStream');
              }
              // 音量計測の開始
              startVolumeMeasurement();
              sendResponse({success: true});
            }).catch(err => {
              console.log('Error:', err);
              sendResponse({success: false, error: err.toString()});  // エラーを示す
            });
            return true; // このリスナーが非同期に応答することを示す（∵「Unchecked runtime.lastError: A listener indicated an asynchronous response by returning true, but the message channel closed before a response was received」を回避）
          }
        });
      } catch (error) {
        console.log("Error fetching audio stream:", error);
        return;
      }
    }
  };

  const onDataAvailable = function(e) {
    // 音声データが利用可能になった時に呼ばれる
    audioChunks.push(e.data);
  };

  const onStop = function(e) {
    if (audioChunks.length === 0) return;
    // リアルタイム文字起こしでは chunk ごとに呼び出されるが、このアプリでは録音終了時に呼び出される
    // audioChunksをBlobとして連結
    const audioDataWebm = new Blob(audioChunks, { type: 'audio/webm' });
    const reader = new FileReader();
    reader.onload = function(event) {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      audioContext.decodeAudioData(event.target.result).then(audioBuffer => {
        // webm → mp3 に変換
        const leftChannel = convertChannel(audioBuffer.getChannelData(0));
        const rightChannel = convertChannel(audioBuffer.getChannelData(1));
        const mp3encoder = new lamejs.Mp3Encoder(2, audioBuffer.sampleRate, 128); // 2 はステレオ

        const mp3Data = [];
        const blockSize = 1152;
        for (let i = 0; i < leftChannel.length; i += blockSize) {
          const leftChunk = leftChannel.subarray(i, i + blockSize);
          const rightChunk = rightChannel.subarray(i, i + blockSize);
          const mp3buf = mp3encoder.encodeBuffer(leftChunk, rightChunk);
          if (mp3buf.length > 0) {
            mp3Data.push(new Int8Array(mp3buf));
          }
        }
        const mp3buf = mp3encoder.flush();
        if (mp3buf.length > 0) {
          mp3Data.push(new Int8Array(mp3buf));
        }
        // mp3 を保存（audioDataMp3 を仮 URL に置き、一時的な <a> から downlaod）
        var filename = document.getElementById('filename').value;
        const audioDataMp3 = new Blob(mp3Data, {type: "audio/mp3"});
        const audioUrl = URL.createObjectURL(audioDataMp3);
        const a = document.createElement("a");
        a.style = "display: none";
        a.href = audioUrl;
        a.download = filename + "_separeted_" + getFormattedDate() + ".mp3";
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(audioUrl);
      }).catch(error => {
        console.error('Decoding error:', error);
      });
    };
    reader.readAsArrayBuffer(audioDataWebm);
  };

  function getFormattedDate() {
      var now = new Date();
      var year = now.getFullYear();
      var month = (now.getMonth() + 1).toString().padStart(2, '0');
      var day = now.getDate().toString().padStart(2, '0');
      var hours = now.getHours().toString().padStart(2, '0');
      var minutes = now.getMinutes().toString().padStart(2, '0');
      var seconds = now.getSeconds().toString().padStart(2, '0');
      return year + month + day + hours + minutes + seconds;
  }

  function convertChannel(float32Array) {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      int16Array[i] = convertSample(float32Array[i]);
    }
    return int16Array;
  }

  function convertSample(sample) {
    return (sample * 32767);  // float32からint16に変換
  }

  var volumeIntervalId = null;

  function startVolumeMeasurement() {
    if (volumeIntervalId !== null) {
      clearInterval(volumeIntervalId);
    }
    volumeIntervalId = setInterval(calculateVolumes, 100);
  }

  function stopVolumeMeasurement() {
    if (volumeIntervalId !== null) {
      clearInterval(volumeIntervalId);
      volumeIntervalId = null;
      document.getElementById('volumeValueMic').innerText = "　";
      document.getElementById('volumeValueSpeaker').innerText = "　";
    }
  }

  function calculateVolumes() {
    if (!analyserMic || !analyserSpeaker) return;
    calculateVolume(analyserMic, 'volumeValueMic');
    calculateVolume(analyserSpeaker, 'volumeValueSpeaker');
  }

  function calculateVolume(analyser, id) {
    if (!analyser) return;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(dataArray);
    var sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      const value = dataArray[i] / 128.0 - 1;
      sum += value * value;
    }
    const rms = Math.sqrt(sum / dataArray.length);
    const volume = Math.max(rms, 0);
    const volumePercentage = (volume * 100).toFixed(0);
    document.getElementById(id).innerText = "|".repeat(volumePercentage);
  }

  function finishRecording() {
    analyserMic = null;
    analyserSpeaker = null;
    // 音量計測の終了(stop()前に終了させておかないとエラーになる)
    stopVolumeMeasurement();
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    isRecording = false;
    streams.forEach(stream => stream.getTracks().forEach(track => track.stop()));
    streams = [];
    audioChunks = [];
    audioContext = null;
    mediaStreamSourceMic = null;
    mediaStreamSourceSpeaker = null;
    merger = null;
    mediaStreamDestination = null;
    recordButton.textContent = '音声録音開始';
  }
}

window.onload = popup_run;
