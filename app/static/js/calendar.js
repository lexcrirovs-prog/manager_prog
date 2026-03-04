/**
 * Простой календарь отгрузок.
 * Загружает события через /api/calendar-events и рендерит месячную сетку.
 */
(function() {
    const calendarEl = document.getElementById('shipment-calendar');
    if (!calendarEl) return;

    let currentDate = new Date();
    let events = [];

    async function loadEvents() {
        try {
            const resp = await fetch('/api/calendar-events');
            events = await resp.json();
        } catch (e) {
            console.error('Ошибка загрузки событий календаря:', e);
        }
        renderCalendar();
    }

    function renderCalendar() {
        const year = currentDate.getFullYear();
        const month = currentDate.getMonth();
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDow = (firstDay.getDay() + 6) % 7; // Пн = 0

        const monthNames = [
            'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ];

        let html = `
            <div class="flex items-center justify-between mb-4">
                <button id="cal-prev" class="btn-primary px-3 py-1 rounded text-sm">&larr;</button>
                <span class="font-semibold text-lg">${monthNames[month]} ${year}</span>
                <button id="cal-next" class="btn-primary px-3 py-1 rounded text-sm">&rarr;</button>
            </div>
            <div class="grid grid-cols-7 gap-1 text-center text-xs font-medium mb-1" style="color: var(--color-text-secondary)">
                <div>Пн</div><div>Вт</div><div>Ср</div><div>Чт</div><div>Пт</div><div>Сб</div><div>Вс</div>
            </div>
            <div class="grid grid-cols-7 gap-1">
        `;

        // Пустые ячейки до начала месяца
        for (let i = 0; i < startDow; i++) {
            html += '<div class="h-20 rounded"></div>';
        }

        for (let day = 1; day <= lastDay.getDate(); day++) {
            const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            const cellDate = new Date(year, month, day);
            const isToday = cellDate.getTime() === today.getTime();
            const dayEvents = events.filter(e => e.date === dateStr);

            let cellClass = 'h-20 rounded p-1 text-xs border';
            cellClass += isToday ? ' border-2' : '';
            let cellStyle = `border-color: ${isToday ? 'var(--color-primary)' : 'var(--color-border)'}; background: var(--color-card);`;

            html += `<div class="${cellClass}" style="${cellStyle}">`;
            html += `<div class="font-medium mb-1" style="color: ${isToday ? 'var(--color-primary)' : 'var(--color-text)'}">${day}</div>`;

            for (const ev of dayEvents.slice(0, 2)) {
                html += `<div class="truncate rounded px-1 mb-0.5 text-white" style="background:${ev.color}; font-size:0.65rem;" title="${ev.title} — ${ev.manager}">${ev.title}</div>`;
            }
            if (dayEvents.length > 2) {
                html += `<div class="text-center" style="color: var(--color-text-secondary); font-size:0.6rem;">+${dayEvents.length - 2}</div>`;
            }

            html += '</div>';
        }

        html += '</div>';
        calendarEl.innerHTML = html;

        // Навигация
        document.getElementById('cal-prev')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() - 1);
            renderCalendar();
        });
        document.getElementById('cal-next')?.addEventListener('click', () => {
            currentDate.setMonth(currentDate.getMonth() + 1);
            renderCalendar();
        });
    }

    loadEvents();
})();
