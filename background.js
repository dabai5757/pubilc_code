// chrome-rec/background.js

let popupWindowId = null;

chrome.action.onClicked.addListener(function(tab) {
  // 直近の popup がまだ開いているか確認
  if (popupWindowId === null) {
    // 直近の popup がない
    createPopupWindow();
  } else {
    // 直近の popup がまだ開いている
    chrome.windows.get(popupWindowId, {populate: true}, function(window) {
      if (chrome.runtime.lastError) {
        // popup が open していないので、popup を開く
        createPopupWindow();
      } else {
        // popup を最前面に表示する
        chrome.windows.update(popupWindowId, {focused: true});
      }
    });
  }
});

function createPopupWindow() {
  chrome.windows.create({
    url: "popup.html",
    width: 800,
    height: 640,
    left: 100,
    top:100,
    focused: true,
    type: "popup"
  }, function(window) {
    popupWindowId = window.id;
  });
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'capture_audio') {
    // 'audio' だけ取得することはできなさそうなので、「画面キャプチャ（システムの音声も共有）」を選択し、後で音声のみ取り出す。
    // 'screen' だと画面選択時に「システムの音声も共有する」にしないと track に audio が含まれないので注意（セキュリティのため？）
    console.log("sender.tab:", sender.tab);
    chrome.desktopCapture.chooseDesktopMedia(['screen', 'audio'], sender.tab, streamId => {
      if (chrome.runtime.lastError) {
        console.error("Runtime Error:", chrome.runtime.lastError.message);
        sendResponse({ error: chrome.runtime.lastError.message });  // エラーを示す
        return;
      } else if (!streamId) {  // streamIdがない場合（キャンセルなど）
        sendResponse({cancelled: true});  // キャンセル処理を求める
        return;
      }
      // sender.tab.id は署名として必要
      chrome.tabs.sendMessage(sender.tab.id, { streamId }, (response) => {
        if (chrome.runtime.lastError) {
          console.error("SendMessage Error:", chrome.runtime.lastError.message);
          sendResponse({ error: chrome.runtime.lastError.message });  // エラーを示す
          return;
        }
        if(response && response.error) {
          console.error("SendMessage Response Error:", response.error);
          sendResponse({ error: response.error });  // エラーを示す
          return;
        }
        sendResponse({ success: true });  // 成功を示す
      });
    });
    return true; // `Unchecked runtime.lastError: The message port closed before a response was received.`を避けるため必要
  }
});
