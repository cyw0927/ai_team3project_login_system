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

    if (tbody && headingToolbar && !emptyRow) {
      const rows = () => Array.from(tbody.querySelectorAll("tr"));
      const text = (row, index) => (row.children[index]?.textContent || "").trim();

      // 목록 상단의 '전체/현재' 표시는 과거 템플릿의 paginator 접근 때문에
      // 0명으로 보일 수 있었다. 카드의 실제 DB 전체 수강생 수를 기준으로
      // '전체 등록 / 현재 페이지' 의미가 명확하도록 보정한다.
      const statCards = Array.from(document.querySelectorAll(".ax-mini-stat"));
      const totalCard = statCards.find((card) =>
        (card.textContent || "").includes("전체 수강생")
      );
      const totalValue = totalCard?.querySelector(".ax-mini-stat-value")?.textContent?.trim();
      const countBadge = headingToolbar.querySelector(".badge.bg-light.text-primary.border");
      if (countBadge && totalValue && /^\d+$/.test(totalValue)) {
        countBadge.textContent = `전체 등록 ${totalValue}명 · 현재 페이지 ${rows().length}명`;
      }

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
        const sortedRows = rows().sort(comparator);
        sortedRows.forEach((row) => {
          tbody.appendChild(row);
          row.classList.remove("ax-sort-flash");
          void row.offsetWidth;
          row.classList.add("ax-sort-flash");
        });
      });
    }
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
