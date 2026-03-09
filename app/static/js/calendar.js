/**
 * Календарь отгрузок с цветовой кодировкой менеджеров.
 *
 * События загружаются из /api/calendar-events.
 * Легенда менеджеров — из /api/calendar-events/managers.
 * Каждый менеджер имеет уникальный фон; белый текст контрастен на всех цветах палитры.
 */
(function() {
    const calendarEl = document.getElementById('shipment-calendar');
    if (!calendarEl) return;

    let currentDate = new Date();
    let events = [];

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

    /**
     * Рендерит легенду менеджеров под календарём.
     * @param {Array<{id, name, color, text_color}>} managers
     */
    function renderLegend(managers) {
        const legendEl = document.getElementById('calendar-legend');
        if (!legendEl || !managers || managers.length === 0) return;

        const items = managers.map(m => `
            <span class="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full"
                  style="background:${m.color}; color:${m.text_color || '#fff'};">
                ${escapeHtml(m.name)}
            </span>
        `).join('');

        legendEl.innerHTML = `
            <div class="mt-3 pt-3 flex flex-wrap gap-2" style="border-top: 1px solid var(--color-border);">
                <span class="text-xs self-center" style="color: var(--color-text-secondary);">Менеджеры:</span>
                ${items}
            </div>
        `;
    }

    function renderCalendar() {
        const year  = currentDate.getFullYear();
        const month = currentDate.getMonth();
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const firstDay = new Date(year, month, 1);
        const lastDay  = new Date(year, month + 1, 0);
        const startDow = (firstDay.getDay() + 6) % 7; // Пн = 0

        const monthNames = [
            'Январь','Февраль','Март','Апрель','Май','Июнь',
            'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
        ];

        let html = `
            <div class="flex items-center justify-between mb-4">
                <button id="cal-prev" class="btn-primary px-3 py-1 rounded text-sm">&larr;</button>
                <span class="font-semibold text-lg">${monthNames[month]} ${year}</span>
                <button id="cal-next" class="btn-primary px-3 py-1 rounded text-sm">&rarr;</button>
            </div>
            <div class="grid grid-cols-7 gap-1 text-center text-xs font-medium mb-1"
                 style="color: var(--color-text-secondary)">
                <div>Пн</div><div>Вт</div><div>Ср</div><div>Чт</div><div>Пт</div><div>Сб</div><div>Вс</div>
            </div>
            <div class="grid grid-cols-7 gap-1">
        `;

        // Пустые ячейки до первого дня месяца
        for (let i = 0; i < startDow; i++) {
            html += '<div class="h-20 rounded"></div>';
        }

        for (let day = 1; day <= lastDay.getDate(); day++) {
            const dateStr  = `${year}-${String(month + 1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
            const cellDate = new Date(year, month, day);
            const isToday  = cellDate.getTime() === today.getTime();
            const dayEvents = events.filter(e => e.date === dateStr);

            const borderStyle = isToday
                ? `border: 2px solid var(--color-primary);`
                : `border: 1px solid var(--color-border);`;

            html += `<div class="h-20 rounded p-1 text-xs"
                          style="${borderStyle} background: var(--color-card);">`;
            html += `<div class="font-medium mb-1"
                          style="color: ${isToday ? 'var(--color-primary)' : 'var(--color-text)'}">
                         ${day}
                     </div>`;

            // Показываем до 2 событий, остальные — счётчик
            for (const ev of dayEvents.slice(0, 2)) {
                const label = escapeHtml(ev.manager
                    ? `${ev.title} (${ev.manager})`
                    : ev.title);
                html += `<div class="truncate rounded px-1 mb-0.5"
                              style="background:${ev.color}; color:#fff; font-size:0.65rem;"
                              title="${label}">${escapeHtml(ev.title)}</div>`;
            }
            if (dayEvents.length > 2) {
                html += `<div class="text-center"
                              style="color: var(--color-text-secondary); font-size:0.6rem;">
                             +${dayEvents.length - 2}
                         </div>`;
            }

            html += '</div>';
        }

        html += '</div>';
        calendarEl.innerHTML = html;

        document.getElementById('cal-prev')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            renderCalendar();
        });
        document.getElementById('cal-next')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            renderCalendar();
        });
    }

    /** Экранирует HTML-спецсимволы в строке. */
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    loadEvents();
})();
