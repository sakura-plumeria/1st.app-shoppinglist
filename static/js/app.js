(function () {
  const bar = document.getElementById('undoBar');
  if (!bar) return;

  const itemId = bar.dataset.itemId;
  const token = bar.dataset.token;
  const remain = parseInt(bar.dataset.remainingMs || '0', 10);
  const finalizeUrl = bar.dataset.finalizeUrl;

  // 期限に合わせて自動確定（画面から消し → サーバへ確定通知）
  const timer = setTimeout(() => {
    // 1) 見た目を先に消す
    try { bar.remove(); } catch (e) {}
    const li = document.getElementById('item-' + itemId);
    if (li) try { li.remove(); } catch (e) {}

    // サーバに最終確定を通知（購入=削除）
    try {
      fetch(finalizeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ item_id: itemId, token })
      });
    } catch (e) {}
  }, Math.max(0, remain));

  // Undoボタンを押した場合はタイマー停止
  const form = bar.querySelector('form');
  if (form) {
    form.addEventListener('submit', () => clearTimeout(timer));
  }
})();