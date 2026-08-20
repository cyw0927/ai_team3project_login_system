document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form.score-weight-form");
  if (!form) return;

  const readValue = (name, fallback) => {
    const input = form.querySelector(`input[name='${name}']`);
    const value = Number.parseInt(input?.value ?? "", 10);
    return Number.isFinite(value) ? value : fallback;
  };

  const initialTeam = readValue("team_weight", 40);
  const initialPersonal = readValue("personal_weight", 30);
  const initialTutor = readValue("tutor_weight", Math.max(0, 100 - initialTeam - initialPersonal));

  form.querySelectorAll(".weight-field, .weight-plus, .weight-equals, [data-score-recommended]").forEach((element) => element.remove());

  const submitButton = form.querySelector("button[type='submit']");
  if (!submitButton) return;

  const field = (label, name, value) => {
    const wrap = document.createElement("div");
    wrap.className = "weight-field";
    wrap.innerHTML = `
      <label>${label}</label>
      <div class="input-group">
        <input class="form-control" type="number" min="0" max="100" name="${name}" value="${value}" required>
        <span class="input-group-text">%</span>
      </div>`;
    return wrap;
  };

  const plus = () => {
    const element = document.createElement("div");
    element.className = "weight-plus";
    element.textContent = "+";
    return element;
  };

  const equals = document.createElement("div");
  equals.className = "weight-equals";
  equals.textContent = "= 100%";

  const recommended = document.createElement("button");
  recommended.type = "button";
  recommended.className = "btn btn-outline-primary fw-semibold";
  recommended.dataset.scoreRecommended = "1";
  recommended.innerHTML = '<i class="bi bi-magic me-1"></i> 권장 40:30:30';

  const elements = [
    field("학생 팀 평가", "team_weight", initialTeam),
    plus(),
    field("동료 개인 평가", "personal_weight", initialPersonal),
    plus(),
    field("튜터 팀 평가", "tutor_weight", initialTutor),
    equals,
    recommended,
  ];
  elements.forEach((element) => form.insertBefore(element, submitButton));

  recommended.addEventListener("click", () => {
    form.querySelector("input[name='team_weight']").value = 40;
    form.querySelector("input[name='personal_weight']").value = 30;
    form.querySelector("input[name='tutor_weight']").value = 30;
  });

  form.addEventListener("submit", (event) => {
    const team = readValue("team_weight", 0);
    const personal = readValue("personal_weight", 0);
    const tutor = readValue("tutor_weight", 0);
    if (team + personal + tutor !== 100) {
      event.preventDefault();
      window.alert(`가중치 합계가 ${team + personal + tutor}%입니다. 세 항목 합계를 100%로 맞춰주세요.`);
    }
  });

  const card = form.closest(".score-control-card");
  const chip = card?.querySelector(".score-policy-chip");
  if (chip) {
    chip.textContent = `팀 ${initialTeam}% · 개인 ${initialPersonal}% · 튜터 ${initialTutor}%`;
  }

  const headingCopy = card?.querySelector(".section-heading-row p");
  if (headingCopy) {
    headingCopy.textContent = "학생 팀 평가, 동료 개인 평가, 튜터 팀 평가 비중을 조정합니다. 세 항목 합계는 100%입니다.";
  }
});
