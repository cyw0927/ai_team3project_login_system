document.addEventListener("DOMContentLoaded", () => {
  const desktop = document.querySelector(".ax-sidebar-toggle");
  const mobile = document.querySelector(".ax-mobile-sidebar-toggle");

  if (desktop) {
    desktop.addEventListener("click", () => {
      document.body.classList.toggle("ax-sidebar-mini");
    });
  }

  if (mobile) {
    mobile.addEventListener("click", () => {
      document.body.classList.toggle("ax-sidebar-open");
    });
  }

  document.addEventListener("click", (event) => {
    if (window.innerWidth >= 992) return;
    if (!document.body.classList.contains("ax-sidebar-open")) return;

    const sidebar = document.querySelector(".ax-purple-sidebar");
    if (sidebar && !sidebar.contains(event.target) && !mobile?.contains(event.target)) {
      document.body.classList.remove("ax-sidebar-open");
    }
  });

  // 관리자 > 수강생 목록: 현재 표시된 수강생을 즉시 정렬한다.
  const studentTable = document.querySelector("table.ax-work-table");
  const studentHeading = Array.from(document.querySelectorAll("h5")).find(
    (element) => element.textContent.trim() === "수강생 목록"
  );

  if (studentTable && studentHeading) {
    const tbody = studentTable.querySelector("tbody");
    const headingToolbar = studentHeading.closest(".ax-management-toolbar");
    const emptyRow = tbody?.querySelector("td[colspan]");

    if (tbody && headingToolbar) {
      const rows = () => Array.from(tbody.querySelectorAll("tr")).filter((row) => !row.querySelector("td[colspan]"));
      const text = (row, index) => (row.children[index]?.textContent || "").trim();

      const statCards = Array.from(document.querySelectorAll(".ax-mini-stat"));
      const totalCard = statCards.find((card) =>
        (card.textContent || "").includes("전체 수강생")
      );
      const totalValue = totalCard?.querySelector(".ax-mini-stat-value")?.textContent?.trim();
      const countBadge = headingToolbar.querySelector(".badge.bg-light.text-primary.border");
      if (countBadge && totalValue && /^\d+$/.test(totalValue)) {
        countBadge.textContent = `전체 등록 ${totalValue}명 · 현재 페이지 ${rows().length}명`;
      }

      if (!emptyRow) {
        const sortWrap = document.createElement("div");
        sortWrap.className = "ax-student-sort-wrap";
        sortWrap.innerHTML = `
          <label for="axStudentSort"><i class="bi bi-sort-down me-1"></i>정렬</label>
          <select id="axStudentSort" class="form-select form-select-sm" aria-label="수강생 정렬">
            <option value="name-asc">이름 가나다순</option>
            <option value="name-desc">이름 역순</option>
            <option value="team-asc">팀 이름순</option>
            <option value="missing-desc">미제출 많은 순</option>
            <option value="status-asc">상태순</option>
            <option value="id-asc">ID 낮은 순</option>
            <option value="id-desc">ID 높은 순</option>
          </select>`;
        headingToolbar.appendChild(sortWrap);

        const select = sortWrap.querySelector("select");
        const missingCount = (row) => {
          const match = text(row, 6).match(/미제출\s*(\d+)건/);
          return match ? Number(match[1]) : 0;
        };

        const comparators = {
          "name-asc": (a, b) => text(a, 2).localeCompare(text(b, 2), "ko"),
          "name-desc": (a, b) => text(b, 2).localeCompare(text(a, 2), "ko"),
          "team-asc": (a, b) => text(a, 5).localeCompare(text(b, 5), "ko") || text(a, 2).localeCompare(text(b, 2), "ko"),
          "missing-desc": (a, b) => missingCount(b) - missingCount(a) || text(a, 2).localeCompare(text(b, 2), "ko"),
          "status-asc": (a, b) => text(a, 6).localeCompare(text(b, 6), "ko") || text(a, 2).localeCompare(text(b, 2), "ko"),
          "id-asc": (a, b) => Number(text(a, 1)) - Number(text(b, 1)),
          "id-desc": (a, b) => Number(text(b, 1)) - Number(text(a, 1)),
        };

        select.addEventListener("change", () => {
          const comparator = comparators[select.value] || comparators["name-asc"];
          rows().sort(comparator).forEach((row) => {
            tbody.appendChild(row);
            row.classList.remove("ax-sort-flash");
            void row.offsetWidth;
            row.classList.add("ax-sort-flash");
          });
        });
      }

      // 평가 완료/미제출은 현재 페이지를 JS로 숨기는 대신 서버에서 전체 결과를 다시 필터링한다.
      const pageUrl = new URL(window.location.href);
      const currentEvalStatus = pageUrl.searchParams.get("eval_status") || "";
      const filterBar = document.createElement("div");
      filterBar.className = "d-flex gap-2 flex-wrap align-items-center mt-3";
      filterBar.innerHTML = `
        <span class="small fw-semibold text-muted me-1"><i class="bi bi-funnel me-1"></i>평가 상태</span>
        <button type="button" class="btn btn-sm ${currentEvalStatus === "" ? "btn-primary" : "btn-outline-secondary"}" data-eval-filter="">전체</button>
        <button type="button" class="btn btn-sm ${currentEvalStatus === "complete" ? "btn-success" : "btn-outline-success"}" data-eval-filter="complete"><i class="bi bi-check-circle me-1"></i>평가 완료만</button>
        <button type="button" class="btn btn-sm ${currentEvalStatus === "missing" ? "btn-danger" : "btn-outline-danger"}" data-eval-filter="missing"><i class="bi bi-exclamation-circle me-1"></i>미제출만</button>`;
      headingToolbar.parentElement?.insertBefore(filterBar, headingToolbar.nextSibling);

      filterBar.querySelectorAll("[data-eval-filter]").forEach((button) => {
        button.addEventListener("click", () => {
          const nextUrl = new URL(window.location.href);
          const value = button.dataset.evalFilter || "";
          if (value) nextUrl.searchParams.set("eval_status", value);
          else nextUrl.searchParams.delete("eval_status");
          nextUrl.searchParams.delete("page");
          window.location.assign(nextUrl.toString());
        });
      });
    }
  }

  // 관리자 > 팀/개인 점수: 숫자 열을 높은 순/낮은 순으로 즉시 정렬한다.
  const pageTitle = document.querySelector(".page-title")?.textContent?.trim() || "";
  const scoreTable = document.querySelector("table.ax-work-table");
  if (scoreTable && (pageTitle.includes("개인 점수") || pageTitle.includes("팀 점수"))) {
    const tbody = scoreTable.querySelector("tbody");
    const rows = () => Array.from(tbody?.querySelectorAll("tr") || []).filter((row) => !row.querySelector("td[colspan]"));
    const sectionHead = scoreTable.closest(".ax-work-card")?.querySelector(".ax-section-head");

    if (tbody && sectionHead && rows().length) {
      const isPersonal = pageTitle.includes("개인 점수");
      const sorter = document.createElement("select");
      sorter.className = "form-select form-select-sm ms-auto";
      sorter.style.maxWidth = "220px";
      sorter.setAttribute("aria-label", "점수 정렬");
      sorter.innerHTML = isPersonal
        ? `<option value="name-asc">이름 가나다순</option>
           <option value="personal-desc">개인 점수 높은 순</option>
           <option value="personal-asc">개인 점수 낮은 순</option>
           <option value="team-desc">팀 점수 높은 순</option>
           <option value="team-asc">팀 점수 낮은 순</option>
           <option value="final-desc">최종 점수 높은 순</option>
           <option value="final-asc">최종 점수 낮은 순</option>
           <option value="count-desc">받은 평가 많은 순</option>
           <option value="count-asc">받은 평가 적은 순</option>`
        : `<option value="rank-asc">순위순</option>
           <option value="score-desc">평균 점수 높은 순</option>
           <option value="score-asc">평균 점수 낮은 순</option>
           <option value="count-desc">제출 평가 많은 순</option>
           <option value="count-asc">제출 평가 적은 순</option>
           <option value="name-asc">팀 이름순</option>`;
      sectionHead.insertBefore(sorter, sectionHead.lastElementChild);

      const cellText = (row, index) => (row.children[index]?.textContent || "").trim();
      const number = (row, index, fallback) => {
        const parsed = Number.parseFloat(cellText(row, index).replace(/[^0-9.-]/g, ""));
        return Number.isFinite(parsed) ? parsed : fallback;
      };
      const numericSort = (index, direction) => (a, b) => {
        const fallback = direction === "desc" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
        const av = number(a, index, fallback);
        const bv = number(b, index, fallback);
        return direction === "desc" ? bv - av : av - bv;
      };
      const comparators = isPersonal
        ? {
            "name-asc": (a, b) => cellText(a, 0).localeCompare(cellText(b, 0), "ko"),
            "personal-desc": numericSort(2, "desc"),
            "personal-asc": numericSort(2, "asc"),
            "team-desc": numericSort(3, "desc"),
            "team-asc": numericSort(3, "asc"),
            "final-desc": numericSort(4, "desc"),
            "final-asc": numericSort(4, "asc"),
            "count-desc": numericSort(1, "desc"),
            "count-asc": numericSort(1, "asc"),
          }
        : {
            "rank-asc": numericSort(0, "asc"),
            "score-desc": numericSort(3, "desc"),
            "score-asc": numericSort(3, "asc"),
            "count-desc": numericSort(2, "desc"),
            "count-asc": numericSort(2, "asc"),
            "name-asc": (a, b) => cellText(a, 1).localeCompare(cellText(b, 1), "ko"),
          };

      sorter.addEventListener("change", () => {
        const comparator = comparators[sorter.value];
        if (!comparator) return;
        rows().sort(comparator).forEach((row) => tbody.appendChild(row));
      });
    }
  }

  // 관리자 > 자동 팀 편성: A/B/C/D 누적 경계값을 직접 조정한다.
  const autoPreviewForm = document.getElementById("autoPreviewForm");
  const potGuide = autoPreviewForm?.querySelector(".pot-rule-guide");
  if (autoPreviewForm && potGuide) {
    const totalText = autoPreviewForm.querySelector(".static-value strong")?.textContent?.trim();
    const totalStudents = Number.parseInt(totalText || "0", 10) || 0;
    const storageKey = `ax-pot-cutoffs-${autoPreviewForm.querySelector("input[name='round_id']")?.value || "default"}`;
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    } catch (_) {
      saved = null;
    }
    const initial = Array.isArray(saved) && saved.length === 3 ? saved : [20, 50, 80];

    potGuide.innerHTML = `
      <div class="w-100 mb-2">
        <strong class="d-block mb-1">포트 경계 직접 설정</strong>
        <small class="text-muted">숫자는 누적 상한입니다. 예: 20 / 50 / 80 → A 0~20%, B 20~50%, C 50~80%, D 80~100%.</small>
      </div>
      <div class="d-flex gap-2 flex-wrap w-100" id="potCutoffControls">
        <label class="input-group input-group-sm" style="max-width:150px"><span class="input-group-text pot-a">A 끝</span><input class="form-control" type="number" id="potACutoff" min="1" max="97" value="${initial[0]}"><span class="input-group-text">%</span></label>
        <label class="input-group input-group-sm" style="max-width:150px"><span class="input-group-text pot-b">B 끝</span><input class="form-control" type="number" id="potBCutoff" min="2" max="98" value="${initial[1]}"><span class="input-group-text">%</span></label>
        <label class="input-group input-group-sm" style="max-width:150px"><span class="input-group-text pot-c">C 끝</span><input class="form-control" type="number" id="potCCutoff" min="3" max="99" value="${initial[2]}"><span class="input-group-text">%</span></label>
      </div>
      <div class="w-100 mt-2 d-flex gap-2 flex-wrap" id="potBandSummary"></div>
      <small class="w-100 mt-1" id="potCountSummary"></small>`;

    ["pot_a_cutoff", "pot_b_cutoff", "pot_c_cutoff"].forEach((name, index) => {
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = name;
      hidden.value = initial[index];
      autoPreviewForm.appendChild(hidden);
    });

    const aInput = document.getElementById("potACutoff");
    const bInput = document.getElementById("potBCutoff");
    const cInput = document.getElementById("potCCutoff");
    const bandSummary = document.getElementById("potBandSummary");
    const countSummary = document.getElementById("potCountSummary");
    const potRuleCopy = autoPreviewForm.querySelector(".pot-rule-option small");

    const calculateCounts = (a, b, c) => {
      const aCount = Math.ceil(totalStudents * a / 100);
      const bCount = Math.max(Math.ceil(totalStudents * b / 100) - aCount, 0);
      const cCount = Math.max(Math.ceil(totalStudents * c / 100) - Math.ceil(totalStudents * b / 100), 0);
      const dCount = Math.max(totalStudents - Math.ceil(totalStudents * c / 100), 0);
      return { A: aCount, B: bCount, C: cCount, D: dCount };
    };

    const refreshPotUi = () => {
      const a = Number.parseInt(aInput.value, 10);
      const b = Number.parseInt(bInput.value, 10);
      const c = Number.parseInt(cInput.value, 10);
      const valid = Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(c) && 0 < a && a < b && b < c && c < 100;
      [aInput, bInput, cInput].forEach((input) => input.classList.toggle("is-invalid", !valid));
      autoPreviewForm.querySelector("button[type='submit']").disabled = !valid;
      if (!valid) {
        bandSummary.innerHTML = '<span class="text-danger small fw-semibold">0 &lt; A &lt; B &lt; C &lt; 100 순서로 입력하세요.</span>';
        countSummary.textContent = "";
        return;
      }
      const counts = calculateCounts(a, b, c);
      bandSummary.innerHTML = `
        <span class="badge bg-light text-dark border">A 0~${a}%</span>
        <span class="badge bg-light text-dark border">B ${a}~${b}%</span>
        <span class="badge bg-light text-dark border">C ${b}~${c}%</span>
        <span class="badge bg-light text-dark border">D ${c}~100%</span>`;
      countSummary.textContent = totalStudents
        ? `활성 ${totalStudents}명에 모두 Seed가 있다고 가정하면 A ${counts.A}명 · B ${counts.B}명 · C ${counts.C}명 · D ${counts.D}명입니다. 실제 첫 회차에는 이전 Seed가 없어 랜덤으로 대체될 수 있습니다.`
        : "활성 수강생 수를 확인할 수 없습니다.";
      if (potRuleCopy) potRuleCopy.textContent = `A ${a}% · B ${b}% · C ${c}% 누적 경계로 포트별 랜덤 추첨`;
      autoPreviewForm.querySelector("input[name='pot_a_cutoff']").value = a;
      autoPreviewForm.querySelector("input[name='pot_b_cutoff']").value = b;
      autoPreviewForm.querySelector("input[name='pot_c_cutoff']").value = c;
      sessionStorage.setItem(storageKey, JSON.stringify([a, b, c]));
    };

    [aInput, bInput, cInput].forEach((input) => input.addEventListener("input", refreshPotUi));
    refreshPotUi();
  }

  // 관리자 > 평가 결과: 학생 공개 설정을 상단 액션으로 이동하고 요약 줄은 2열로 정리한다.
  const resultToolbarButtons = document.querySelector(".result-toolbar-buttons");
  const publishCard = document.querySelector(".result-publish-card");
  const resultOverview = document.querySelector(".result-overview-grid");
  if (resultToolbarButtons && publishCard) {
    const publishLink = publishCard.querySelector("a[href*='result_settings']");
    if (publishLink) {
      const shortcut = publishLink.cloneNode(true);
      shortcut.className = "btn btn-outline-primary result-publish-shortcut";
      shortcut.innerHTML = '<i class="bi bi-eye me-1"></i> 학생 공개';
      resultToolbarButtons.appendChild(shortcut);
    }
    publishCard.remove();
    resultOverview?.classList.add("result-overview-two-column");
  }
});
