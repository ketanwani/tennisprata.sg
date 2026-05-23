(function () {
  const courtInput = document.querySelector("[data-location-search='true']");
  if (!courtInput) return;

  const addressInput = document.querySelector("#id_court_address");
  const localityInput = document.querySelector("#id_locality");
  const postalInput = document.querySelector("#id_postal_code");
  const latInput = document.querySelector("#id_latitude");
  const lngInput = document.querySelector("#id_longitude");

  const wrapper = document.createElement("div");
  wrapper.className = "location-suggest";
  courtInput.parentNode.append(wrapper);

  const mapsLink = document.createElement("a");
  mapsLink.className = "maps-link";
  mapsLink.target = "_blank";
  mapsLink.rel = "noreferrer";
  mapsLink.hidden = true;
  mapsLink.textContent = "Open selected court in Google Maps";
  courtInput.parentNode.append(mapsLink);

  let latestQuery = "";

  function setLocation(location) {
    courtInput.value = location.name || "";
    if (localityInput) localityInput.value = location.locality || "";
    if (addressInput) addressInput.value = location.address || "";
    if (postalInput) postalInput.value = location.postal_code || "";
    if (latInput) latInput.value = normalizeCoordinate(location.latitude);
    if (lngInput) lngInput.value = normalizeCoordinate(location.longitude);
    wrapper.innerHTML = "";
    updateMapsLink();
  }

  function updateMapsLink() {
    if (latInput && lngInput && latInput.value && lngInput.value) {
      mapsLink.href = `https://www.google.com/maps/search/?api=1&query=${latInput.value},${lngInput.value}`;
      mapsLink.hidden = false;
    } else if (courtInput.value) {
      mapsLink.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(courtInput.value + " Singapore")}`;
      mapsLink.hidden = false;
    }
  }

  function renderSuggestions(results) {
    wrapper.innerHTML = "";
    results.forEach((result) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "location-option";
      button.innerHTML = `<strong>${escapeHtml(result.name)}</strong><span>${escapeHtml(
        [result.address, result.postal_code].filter(Boolean).join(" ")
      )}</span>`;
      button.addEventListener("click", () => setLocation(result));
      wrapper.append(button);
    });
  }

  async function searchOneMap(query) {
    const url = `${window.TENNISPRATA_LOCATION_SEARCH_URL}?q=${encodeURIComponent(query)}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (courtInput.value.trim() === latestQuery) renderSuggestions(payload.results || []);
  }

  courtInput.addEventListener("input", () => {
    const query = courtInput.value.trim();
    latestQuery = query;
    if (addressInput) addressInput.value = "";
    if (localityInput) localityInput.value = "";
    if (postalInput) postalInput.value = "";
    if (latInput) latInput.value = "";
    if (lngInput) lngInput.value = "";
    mapsLink.hidden = true;
    if (query.length < 2) {
      wrapper.innerHTML = "";
      return;
    }
    searchOneMap(query).catch(() => renderSuggestions([]));
  });

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function normalizeCoordinate(value) {
    if (!value) return "";
    const numberValue = Number(value);
    if (Number.isNaN(numberValue)) return "";
    return numberValue.toFixed(6);
  }
})();
