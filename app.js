const STORAGE_KEY = "tennisprata-state-v1";
const RAINY_TERMS = ["showers", "rain", "thundery", "drizzle"];

const seedState = {
  profile: null,
  sessions: [
    {
      id: "tp-" + Math.random().toString(36).slice(2, 8),
      title: "Sunday prata decider",
      date: new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10),
      time: "08:00",
      locality: "Kallang",
      courtDetails: "ActiveSG Kallang Tennis Centre, Court 2",
      cost: "$14 court split",
      hostPair: "Ketan / Aaron",
      challengerPair: "Mira / Sam",
      notes: "Best of 3 short sets. Losers buy egg prata and teh tarik.",
      winner: null,
      createdBy: "demo",
    },
  ],
  leaderboard: {
    "Ketan / Aaron": 12,
    "Mira / Sam": 9,
    "Priya / Daniel": 6,
  },
};

let state = loadState();
let forecasts = {};

const profileForm = document.querySelector("#profileForm");
const sessionForm = document.querySelector("#sessionForm");
const sessionsList = document.querySelector("#sessionsList");
const leaderboardEl = document.querySelector("#leaderboard");
const profileStatus = document.querySelector("#profileStatus");

document.querySelector("#sessionDate").value = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

profileForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.profile = {
    name: document.querySelector("#playerName").value.trim(),
    contact: document.querySelector("#playerContact").value.trim(),
  };
  saveState();
  render();
});

sessionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const session = {
    id: "tp-" + Math.random().toString(36).slice(2, 8),
    title: document.querySelector("#sessionTitle").value.trim(),
    date: document.querySelector("#sessionDate").value,
    time: document.querySelector("#sessionTime").value,
    locality: document.querySelector("#sessionLocality").value,
    courtDetails: document.querySelector("#courtDetails").value.trim(),
    cost: document.querySelector("#sessionCost").value.trim(),
    hostPair: document.querySelector("#hostPair").value.trim(),
    challengerPair: "",
    notes: document.querySelector("#sessionNotes").value.trim(),
    winner: null,
    createdBy: state.profile?.contact || "guest",
  };
  state.sessions.unshift(session);
  state.leaderboard[session.hostPair] ??= 0;
  saveState();
  sessionForm.reset();
  document.querySelector("#sessionDate").value = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  render();
});

async function loadForecasts() {
  try {
    const response = await fetch("https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast");
    const data = await response.json();
    const readings = data?.data?.items?.[0]?.forecasts || [];
    forecasts = readings.reduce((acc, item) => {
      acc[item.area] = item.forecast;
      return acc;
    }, {});
  } catch {
    forecasts = {};
  }
  render();
}

function render() {
  renderProfile();
  renderStats();
  renderSessions();
  renderLeaderboard();
}

function renderProfile() {
  if (!state.profile) {
    profileStatus.textContent = "Sign in to join or create a prata challenge.";
    return;
  }
  document.querySelector("#playerName").value = state.profile.name;
  document.querySelector("#playerContact").value = state.profile.contact;
  profileStatus.textContent = `Signed in as ${state.profile.name}. Session reminders will be sent 24 hours before play in the production app.`;
}

function renderStats() {
  document.querySelector("#activeSessions").textContent = state.sessions.length;
  const top = Object.entries(state.leaderboard).sort((a, b) => b[1] - a[1])[0];
  document.querySelector("#topPair").textContent = top ? top[0] : "-";
}

function renderSessions() {
  sessionsList.innerHTML = "";
  if (state.sessions.length === 0) {
    sessionsList.innerHTML = `<div class="empty">No prata sessions yet. Create the first challenge.</div>`;
    return;
  }

  const template = document.querySelector("#sessionTemplate");
  state.sessions.forEach((session) => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".session-card");
    const forecast = forecasts[session.locality] || "Forecast pending";
    const rainy = RAINY_TERMS.some((term) => forecast.toLowerCase().includes(term));

    node.querySelector("h3").textContent = session.title;
    node.querySelector(".session-meta").textContent =
      `${formatDate(session.date)} at ${session.time} - ${session.locality} - ${session.cost || "No cost listed"}`;
    node.querySelector(".court").textContent = session.courtDetails;
    node.querySelector(".notes").textContent = session.notes || "No extra notes yet.";

    const weatherPill = node.querySelector(".weather-pill");
    weatherPill.textContent = rainy ? `Rain risk: ${forecast}` : `Weather: ${forecast}`;
    weatherPill.classList.toggle("risky", rainy);

    const pairs = node.querySelector(".pairs");
    pairs.append(pairChip(session.hostPair, "Host pair", true));
    if (session.challengerPair) {
      pairs.append(pairChip(session.challengerPair, "Challenger pair", false));
    } else {
      pairs.append(pairChip("Waiting for challengers", "Open slot", false));
    }

    const input = node.querySelector(".challenger-input");
    const joinButton = node.querySelector(".join-button");
    input.value = getInvitePairFromUrl(session.id);
    joinButton.disabled = !state.profile;
    joinButton.addEventListener("click", () => joinSession(session.id, input.value.trim()));

    node.querySelector(".copy-button").addEventListener("click", () => copyInvite(session.id));

    const winnerActions = node.querySelector(".winner-actions");
    [session.hostPair, session.challengerPair].filter(Boolean).forEach((pair) => {
      const button = document.createElement("button");
      button.className = "secondary";
      button.textContent = session.winner === pair ? `${pair} won` : `Mark ${pair} winner`;
      button.addEventListener("click", () => markWinner(session.id, pair));
      winnerActions.append(button);
    });

    if (session.winner) {
      const winner = document.createElement("p");
      winner.className = "status";
      winner.textContent = `${session.winner} earned 3 points. Losing pair owes prata.`;
      card.append(winner);
    }

    sessionsList.append(node);
  });
}

function renderLeaderboard() {
  const rows = Object.entries(state.leaderboard).sort((a, b) => b[1] - a[1]);
  leaderboardEl.innerHTML = rows.length
    ? ""
    : `<div class="empty">Winners will appear here after matches are recorded.</div>`;

  rows.forEach(([pair, points], index) => {
    const row = document.createElement("div");
    row.className = "leader-row";
    row.innerHTML = `<span>${index + 1}. ${pair}</span><strong>${points} pts</strong>`;
    leaderboardEl.append(row);
  });
}

function joinSession(id, pairName) {
  if (!state.profile) {
    alert("Register or login before joining a challenge.");
    return;
  }
  if (!pairName) {
    alert("Add your pair name first.");
    return;
  }
  const session = state.sessions.find((item) => item.id === id);
  session.challengerPair = pairName;
  state.leaderboard[pairName] ??= 0;
  saveState();
  render();
}

function markWinner(id, pairName) {
  const session = state.sessions.find((item) => item.id === id);
  if (session.winner === pairName) return;
  session.winner = pairName;
  state.leaderboard[pairName] = (state.leaderboard[pairName] || 0) + 3;
  saveState();
  render();
}

async function copyInvite(id) {
  const session = state.sessions.find((item) => item.id === id);
  const url = new URL(window.location.href);
  url.searchParams.set("invite", id);
  url.searchParams.set("pair", session.challengerPair || "");
  try {
    await navigator.clipboard.writeText(url.toString());
    alert("Invite link copied.");
  } catch {
    window.prompt("Copy this invite link:", url.toString());
  }
}

function getInvitePairFromUrl(id) {
  const params = new URLSearchParams(window.location.search);
  return params.get("invite") === id ? params.get("pair") || "" : "";
}

function pairChip(name, label, isHost) {
  const chip = document.createElement("span");
  chip.className = `pair-chip${isHost ? " host" : ""}`;
  chip.textContent = `${label}: ${name}`;
  return chip;
}

function formatDate(dateString) {
  return new Intl.DateTimeFormat("en-SG", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(dateString + "T00:00:00"));
}

function loadState() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored ? JSON.parse(stored) : seedState;
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

render();
loadForecasts();
