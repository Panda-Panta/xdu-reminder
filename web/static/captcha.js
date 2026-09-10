document.addEventListener("DOMContentLoaded", () => {
  const stage = document.querySelector(".captcha-stage");
  const piece = document.querySelector(".captcha-piece");
  const track = document.querySelector(".slider-track");
  const thumb = document.querySelector(".slider-thumb");
  const text = document.querySelector(".slider-text");

  if (!track || !thumb || !piece) return;

  let isDragging = false;
  let startX = 0;
  const maxMove = 280 - 44; // 236px

  function onStart(e) {
    isDragging = true;
    startX = e.type.includes("touch") ? e.touches[0].clientX : e.clientX;
    thumb.style.cursor = "grabbing";
    if (text) text.style.opacity = "0";
  }

  function onMove(e) {
    if (!isDragging) return;
    const currentX = e.type.includes("touch") ? e.touches[0].clientX : e.clientX;
    let diff = currentX - startX;
    if (diff < 0) diff = 0;
    if (diff > maxMove) diff = maxMove;

    thumb.style.left = `${diff + 2}px`;
    piece.style.left = `${diff}px`;
  }

  function onEnd() {
    if (!isDragging) return;
    isDragging = false;
    thumb.style.cursor = "pointer";

    const moveLength = parseInt(piece.style.left || "0", 10);
    
    // Submit move length
    fetch("/captcha/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ move_length: moveLength }),
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "ok") {
          window.location.href = "/status";
        } else {
          alert("验证失败，请重试");
          reset();
        }
      })
      .catch((err) => {
        console.error(err);
        reset();
      });
  }

  function reset() {
    thumb.style.left = "2px";
    piece.style.left = "0px";
    if (text) text.style.opacity = "1";
  }

  thumb.addEventListener("mousedown", onStart);
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onEnd);

  thumb.addEventListener("touchstart", onStart, { passive: true });
  window.addEventListener("touchmove", onMove, { passive: true });
  window.addEventListener("touchend", onEnd);
});
