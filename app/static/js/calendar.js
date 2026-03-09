/**
 * Календарь отгрузок и задач менеджеров.
 *
 * Источники данных:
 *   GET /api/calendar-events          → события (отгрузки + задачи ActionItem)
 *   GET /api/calendar-events/managers → легенда цветов менеджеров
 *
 * Функциональность:
 *   - Ячейки дней с событиями заполняются цветными бейджами
 *   - Hover на бейдже → яркость (filter: brightness)
 *   - Клик по ячейке дня → панель деталей под календарём
 *   - Кнопка × или повторный клик на тот же день → закрыть панель
 */
(function () {
    const calendarEl = document.getElementById('shipment-calendar');
    if (!calendarEl) return;

    let currentDate = new Date();
    let events = [];
    let selectedDate = null;  // текущая выбранная ячейка

    const MONTH_NAMES = [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ];
    const PRIORITY_RU = { low: 'Низкий', medium: 'Средний', high: 'Высокий', critical: 'Критический' };
    const STATUS_RU   = {
        pending: 'Ожидает', in_progress: 'В работе', completed: 'Выполнено',
        overdue: 'Просрочено', new: 'Новая', negotiation: 'Переговоры',
        contract: 'Контракт', won: 'Выиграна', lost: 'Проиграна', stale: 'Заморожена',
    };

    // ── Загрузка данных ───────────────────────────────────────────────────

    async function loadEvents() {
        try {
            const [evResp, mgResp] = await Promise.all([
                fetch('/api/calendar-events'),
                fetch('/api/calendar-events/managers'),
            ]);
            events = await evResp.json();
            const managers = await mgResp.json();
            renderLegend(managers);
        } catch (e) {
            console.error('Ошибка загрузки данных календаря:', e);
        }
        renderCalendar();
    }

    // ── Легенда менеджеров ────────────────────────────────────────────────

    function renderLegend(managers) {
        const el = document.getElementById('calendar-legend');
        if (!el || !managers || managers.length === 0) return;
        const badges = managers.map(m =>
            `<span class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full"
                   style="background:${m.color}; color:#fff;">
                 ${escHtml(m.name)}
             </span>`
        ).join('');
        el.innerHTML = `
            <div class="mt-3 pt-3 flex flex-wrap gap-2 items-center"
                 style="border-top:1px solid var(--color-border)">
                <span class="text-xs" style="color:var(--color-text-secondary)">Менеджеры:</span>
                ${badges}
            </div>`;
    }

    // ── Рендер календаря ─────────────────────────────────────────────────

    function renderCalendar() {
        const year     = currentDate.getFullYear();
        const month    = currentDate.getMonth();
        const today    = new Date(); today.setHours(0, 0, 0, 0);
        const firstDay = new Date(year, month, 1);
        const lastDay  = new Date(year, month + 1, 0);
        const startDow = (firstDay.getDay() + 6) % 7;  // Пн=0

        let html = `
            <div class="flex items-center justify-between mb-4">
                <button id="cal-prev" class="btn-primary px-3 py-1 rounded text-sm">&larr;</button>
                <span class="font-semibold text-lg">${MONTH_NAMES[month]} ${year}</span>
                <button id="cal-next" class="btn-primary px-3 py-1 rounded text-sm">&rarr;</button>
            </div>
            <div class="grid grid-cols-7 gap-1 text-center text-xs font-medium mb-1"
                 style="color:var(--color-text-secondary)">
                <div>Пн</div><div>Вт</div><div>Ср</div><div>Чт</div>
                <div>Пт</div><div>Сб</div><div>Вс</div>
            </div>
            <div class="grid grid-cols-7 gap-1">`;

        // пустые ячейки
        for (let i = 0; i < startDow; i++) html += '<div class="h-24 rounded"></div>';

        for (let day = 1; day <= lastDay.getDate(); day++) {
            const dateStr  = `${year}-${pad(month + 1)}-${pad(day)}`;
            const isToday  = new Date(year, month, day).getTime() === today.getTime();
            const isSel    = dateStr === selectedDate;
            const dayEvts  = events.filter(e => e.date === dateStr);
            const hasEvts  = dayEvts.length > 0;

            let border = `border:1px solid var(--color-border);`;
            if (isToday) border = `border:2px solid var(--color-primary);`;
            if (isSel)   border = `border:2px solid #f59e0b; box-shadow:0 0 0 2px #fde68a44;`;

            html += `
                <div class="h-24 rounded p-1 text-xs"
                     style="${border} background:var(--color-card); ${hasEvts ? 'cursor:pointer;' : ''}"
                     onclick="calDayClick('${dateStr}')">
                    <div class="font-medium mb-1"
                         style="color:${isToday ? 'var(--color-primary)' : 'var(--color-text)'}">
                        ${day}
                    </div>`;

            for (const ev of dayEvts.slice(0, 3)) {
                const label = escHtml(`${ev.title}${ev.manager ? ' · ' + ev.manager : ''}`);
                const icon  = ev.type === 'task' ? '✓ ' : '📦 ';
                html += `
                    <div class="truncate rounded px-1 mb-0.5"
                         title="${label}"
                         style="background:${ev.color}; color:#fff; font-size:0.6rem;
                                cursor:pointer; transition:filter 0.15s;"
                         onmouseover="this.style.filter='brightness(1.3)'"
                         onmouseout="this.style.filter=''">
                        ${icon}${escHtml(ev.title)}
                    </div>`;
            }
            if (dayEvts.length > 3) {
                html += `<div style="color:var(--color-text-secondary);font-size:0.6rem;text-align:center">
                             +${dayEvts.length - 3} ещё
                         </div>`;
            }

            html += '</div>';
        }

        html += '</div>';
        calendarEl.innerHTML = html;

        document.getElementById('cal-prev')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            selectedDate = null;
            hideDayDetail();
            renderCalendar();
        });
        document.getElementById('cal-next')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            selectedDate = null;
            hideDayDetail();
            renderCalendar();
        });
    }

    // ── Панель деталей дня ───────────────────────────────────────────────

    /**
     * Обработчик клика по ячейке дня.
     * Повторный клик на тот же день → закрыть панель.
     */
    window.calDayClick = function (dateStr) {
        if (selectedDate === dateStr) {
            selectedDate = null;
            hideDayDetail();
            renderCalendar();
            return;
        }
        selectedDate = dateStr;
        renderCalendar();          // перерисовать, чтобы подсветить выбранную ячейку
        showDayDetail(dateStr);
    };

    function showDayDetail(dateStr) {
        const detailEl = document.getElementById('day-detail');
        if (!detailEl) return;

        const dayEvts = events.filter(e => e.date === dateStr);
        if (dayEvts.length === 0) {
            hideDayDetail();
            return;
        }

        // Формат заголовка: «23 марта 2026»
        const [y, m, d] = dateStr.split('-').map(Number);
        const monthGen = [
            'января','февраля','марта','апреля','мая','июня',
            'июля','августа','сентября','октября','ноября','декабря',
        ];
        const dateTitle = `${d} ${monthGen[m - 1]} ${y}`;

        let cardsHtml = dayEvts.map(ev => {
            const typeLabel = ev.type === 'task' ? 'Задача' : 'Отгрузка';
            const priority  = ev.priority ? (PRIORITY_RU[ev.priority] || ev.priority) : null;
            const status    = ev.status   ? (STATUS_RU[ev.status]   || ev.status)   : null;

            return `
                <div class="p-3 rounded-lg mb-2"
                     style="border-left:4px solid ${ev.color}; background:var(--color-bg);">
                    <div class="flex items-start justify-between gap-2">
                        <div class="font-semibold text-sm">${escHtml(ev.title)}</div>
                        <span class="text-xs px-2 py-0.5 rounded-full shrink-0"
                              style="background:${ev.color}; color:#fff;">${typeLabel}</span>
                    </div>
                    <div class="text-xs mt-1" style="color:var(--color-text-secondary)">
                        ${escHtml(ev.manager)}${ev.customer ? ' · ' + escHtml(ev.customer) : ''}
                    </div>
                    ${ev.equipment ? `<div class="text-xs mt-0.5" style="color:var(--color-text-secondary)">Оборудование: ${escHtml(ev.equipment)}</div>` : ''}
                    ${ev.description ? `<div class="text-xs mt-1">${escHtml(ev.description)}</div>` : ''}
                    ${ev.amount ? `<div class="text-xs mt-0.5" style="color:var(--color-text-secondary)">Сумма: ${Number(ev.amount).toLocaleString('ru-RU')} ₽</div>` : ''}
                    <div class="flex flex-wrap gap-2 mt-2">
                        ${priority ? `<span class="text-xs px-2 py-0.5 rounded" style="background:var(--color-bg-secondary,#f3f4f6);color:var(--color-text)">Приоритет: ${priority}</span>` : ''}
                        ${status   ? `<span class="text-xs px-2 py-0.5 rounded" style="background:var(--color-bg-secondary,#f3f4f6);color:var(--color-text)">Статус: ${status}</span>`   : ''}
                    </div>
                </div>`;
        }).join('');

        detailEl.innerHTML = `
            <div class="mt-4 p-4 rounded-lg" style="border:1px solid var(--color-border); background:var(--color-card);">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold text-sm">
                        События на <strong>${dateTitle}</strong>
                        <span class="ml-1 text-xs font-normal" style="color:var(--color-text-secondary)">(${dayEvts.length})</span>
                    </h3>
                    <button onclick="calCloseDayDetail()"
                            class="text-xl leading-none hover:opacity-60"
                            style="color:var(--color-text-secondary)"
                            aria-label="Закрыть">&times;</button>
                </div>
                ${cardsHtml}
            </div>`;
        detailEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hideDayDetail() {
        const el = document.getElementById('day-detail');
        if (el) el.innerHTML = '';
    }

    window.calCloseDayDetail = function () {
        selectedDate = null;
        hideDayDetail();
        renderCalendar();
    };

    // ── Утилиты ──────────────────────────────────────────────────────────

    function pad(n) { return String(n).padStart(2, '0'); }

    function escHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    loadEvents();
})();
