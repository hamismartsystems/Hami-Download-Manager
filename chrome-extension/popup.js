const el = document.getElementById("it");
chrome.storage.local.get({ intercept: true }, (s) => { el.checked = s.intercept; });
el.addEventListener("change", () => chrome.storage.local.set({ intercept: el.checked }));
