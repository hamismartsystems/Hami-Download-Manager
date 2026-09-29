const API = "http://127.0.0.1:17321/api/add";

// 1) right-click menu: "Download with HDM"
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "hami-download-manager",
    title: "Download with HDM",
    contexts: ["link", "image", "video", "audio", "selection"]
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  const url = info.linkUrl || info.srcUrl;
  if (url) send(url, null, false);
});

// 2) every download the browser starts is handed over to HDM
chrome.downloads.onCreated.addListener(async (item) => {
  const { intercept } = await chrome.storage.local.get({ intercept: true });
  if (!intercept) return;
  if (!item.url || !/^https?:/i.test(item.url)) return;
  if (item.byExtension) return;
  let id = item.id;
  try {
    await chrome.downloads.cancel(id);
  } catch (e) {}
  const ok = await send(item.url, item.filename, true);
  if (!ok) {
    // HDM is not running -> let the browser do the download instead
    notify("HDM is not running — downloaded with the browser.");
    try {
      await chrome.downloads.download({ url: item.url, filename: item.filename || undefined });
    } catch (e) {}
    return;
  }
  try {
    await chrome.downloads.erase({ id });
  } catch (e) {}
});

function send(url, filename, quiet) {
  return fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url, filename: filename || "" })
  })
    .then((r) => r.ok)
    .then((ok) => {
      if (!ok && !quiet) notify("HDM could not accept this link.");
      return ok;
    })
    .catch(() => {
      if (!quiet) notify("HDM is not running. Start HDM first.");
      return false;
    });
}

function notify(msg) {
  try {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icon.png",
      title: "HAMI Download Manager (HDM)",
      message: msg
    });
  } catch (e) {}
}
