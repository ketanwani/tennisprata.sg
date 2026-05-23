(function () {
  const selects = document.querySelectorAll("select[data-ntrp-slider='true']");
  if (!selects.length) return;

  selects.forEach((select) => {
    const options = Array.from(select.options).filter((option) => option.value);
    if (!options.length) return;

    const currentIndex = Math.max(
      0,
      options.findIndex((option) => option.value === select.value)
    );

    select.classList.add("ntrp-native-select");

    const slider = document.createElement("div");
    slider.className = "ntrp-slider";
    slider.innerHTML = `
      <div class="ntrp-slider-head">
        <strong>${escapeHtml(options[currentIndex].textContent)}</strong>
        <a href="https://www.usta.com/en/home/coach-organize/tennis-tool-center/run-usta-programs/national/understanding-ntrp-ratings.html" target="_blank" rel="noreferrer">What is NTRP?</a>
      </div>
      <input type="range" min="0" max="${options.length - 1}" step="1" value="${currentIndex}">
    `;

    select.after(slider);

    const range = slider.querySelector("input");
    const valueLabel = slider.querySelector("strong");

    function updateValue() {
      const option = options[Number(range.value)];
      select.value = option.value;
      valueLabel.textContent = option.textContent;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    range.addEventListener("input", updateValue);
  });

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
})();
