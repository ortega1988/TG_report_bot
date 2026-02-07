        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();

        document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff');
        document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000');
        document.documentElement.style.setProperty('--tg-theme-hint-color', tg.themeParams.hint_color || '#999999');
        document.documentElement.style.setProperty('--tg-theme-link-color', tg.themeParams.link_color || '#2678b6');
        document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#2678b6');
        document.documentElement.style.setProperty('--tg-theme-button-text-color', tg.themeParams.button_text_color || '#ffffff');
        document.documentElement.style.setProperty('--tg-theme-secondary-bg-color', tg.themeParams.secondary_bg_color || '#f0f0f0');

        if (tg.colorScheme === 'dark') {
            document.body.classList.add('dark-theme');
        }

        // Фикс клавиатуры iOS - скрываем при клике вне полей ввода
        document.addEventListener('click', function(e) {
            const tag = e.target.tagName.toLowerCase();
            if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
                document.activeElement.blur();
            }
        });

        // Глобальное состояние
        let chatId = null;
        let openReportId = null;
        let isAdmin = false;
        let currentPage = 'form';
        let myReports = [];
        let adminReports = [];
        let currentUserReportId = null;
        let currentAdminReportId = null;
        let currentAdminFilter = '';
        let myReportsLoaded = false;
        let adminReportsLoaded = false;

        // Пагинация
        const PAGE_SIZE = 20;
        let myReportsOffset = 0;
        let myReportsHasMore = false;
        let myReportsLoading = false;
        let adminReportsOffset = 0;
        let adminReportsHasMore = false;
        let adminReportsLoading = false;
        let adminStats = { total: 0, new: 0, in_progress: 0, completed: 0 };

        const statusLabels = {
            'new': 'Новая',
            'revision': 'Доработка',
            'in_progress': 'В работе',
            'completed': 'Завершена',
            'trash': 'Отказ'
        };

        // Парсинг start_param для получения chat_id и report_id
        // Форматы: chat_id | chat_id_report_id | admin_chat_id_report_id
        let openAsAdmin = false;
        const startParam = tg.initDataUnsafe?.start_param;
        if (startParam) {
            if (startParam.startsWith('admin_')) {
                openAsAdmin = true;
                const adminParts = startParam.substring(6).split('_');
                if (adminParts.length >= 2 && adminParts[0].startsWith('-')) {
                    const reportIdPart = adminParts[adminParts.length - 1];
                    const chatIdPart = adminParts.slice(0, -1).join('_');
                    chatId = parseInt(chatIdPart);
                    openReportId = parseInt(reportIdPart);
                } else if (adminParts.length === 2) {
                    chatId = parseInt(adminParts[0]);
                    openReportId = parseInt(adminParts[1]);
                }
            } else {
                const parts = startParam.split('_');
                if (parts.length >= 2 && parts[0].startsWith('-')) {
                    // Отрицательный chat_id (группа)
                    const reportIdPart = parts[parts.length - 1];
                    const chatIdPart = parts.slice(0, -1).join('_');
                    chatId = parseInt(chatIdPart);
                    openReportId = parseInt(reportIdPart);
                } else if (parts.length === 2) {
                    chatId = parseInt(parts[0]);
                    openReportId = parseInt(parts[1]);
                } else {
                    chatId = parseInt(startParam);
                }
            }
        }

        async function checkAdmin() {
            try {
                const response = await fetch('/api/check-admin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        chat_id: chatId
                    })
                });
                const result = await response.json();
                if (result.is_admin) {
                    isAdmin = true;
                    document.getElementById('admin-btn').style.display = 'block';

                    if (openAsAdmin && openReportId) {
                        switchPage('admin');
                        return;
                    }

                    if (!openReportId) {
                        switchPage('admin');
                    }
                }

                if (openReportId && !openAsAdmin) {
                    switchPage('my-reports');
                }
            } catch (e) {
                console.log('Admin check failed');
                if (openReportId && !openAsAdmin) {
                    switchPage('my-reports');
                }
            }
        }

        function switchPage(page) {
            currentPage = page;

            document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
            document.getElementById(`page-${page}`).classList.add('active');

            if (page === 'form') {
                document.getElementById('top-buttons').style.display = 'flex';
                updateMainButton();
            } else {
                document.getElementById('top-buttons').style.display = 'none';
                tg.MainButton.hide();
            }

            if (page === 'my-reports' && !myReportsLoaded) {
                loadMyReports();
            } else if (page === 'admin' && !adminReportsLoaded) {
                loadAdminReports();
            }
        }

        // ==================== ФОРМА ====================

        // Установка текущего времени по умолчанию
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        document.getElementById('error_time').value = now.toISOString().slice(0, 16);

        // Группы кнопок выбора (платформа, сервер)
        document.querySelectorAll('.button-group').forEach(group => {
            group.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    group.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                    btn.classList.add('selected');
                    const hiddenInput = group.nextElementSibling;
                    if (hiddenInput && hiddenInput.type === 'hidden') {
                        hiddenInput.value = btn.dataset.value;
                    }
                    updateMainButton();
                });
            });
        });

        // Загрузка файлов
        const MAX_FILES = 10;
        const MAX_FILE_SIZE = 500 * 1024 * 1024;
        let uploadedFiles = [];

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        function updateFilesUI() {
            const filesList = document.getElementById('files-list');
            const filesCounter = document.getElementById('files-counter');

            filesList.innerHTML = '';

            uploadedFiles.forEach((file, index) => {
                const item = document.createElement('div');
                item.className = 'file-item';

                if (file.type.startsWith('image/')) {
                    const img = document.createElement('img');
                    img.src = URL.createObjectURL(file);
                    item.appendChild(img);
                } else {
                    const icon = document.createElement('div');
                    icon.className = 'file-icon';
                    icon.textContent = '\uD83C\uDFAC';
                    item.appendChild(icon);
                }

                const info = document.createElement('div');
                info.className = 'file-info';
                info.innerHTML = `
                    <div class="file-name">${escapeHtml(file.name)}</div>
                    <div class="file-size">${formatFileSize(file.size)}</div>
                `;
                item.appendChild(info);

                const removeBtn = document.createElement('span');
                removeBtn.className = 'remove-file';
                removeBtn.textContent = '\u00D7';
                removeBtn.onclick = () => removeFile(index);
                item.appendChild(removeBtn);

                filesList.appendChild(item);
            });

            if (uploadedFiles.length > 0) {
                filesCounter.textContent = `Выбрано файлов: ${uploadedFiles.length} из ${MAX_FILES}`;
            } else {
                filesCounter.textContent = '';
            }
        }

        function removeFile(index) {
            uploadedFiles.splice(index, 1);
            updateFilesUI();
        }

        function showFileError(message) {
            const errorEl = document.getElementById('file-error');
            errorEl.textContent = message;
            errorEl.classList.add('show');
            setTimeout(() => errorEl.classList.remove('show'), 5000);
        }

        function hideFileError() {
            document.getElementById('file-error').classList.remove('show');
        }

        document.getElementById('media').addEventListener('change', function(e) {
            const input = e.target;
            const newFiles = Array.from(input.files);
            hideFileError();

            for (let i = 0; i < newFiles.length; i++) {
                const file = newFiles[i];

                if (uploadedFiles.length >= MAX_FILES) {
                    showFileError('Максимум ' + MAX_FILES + ' файлов');
                    break;
                }

                if (file.size > MAX_FILE_SIZE) {
                    showFileError('Файл "' + file.name + '" слишком большой. Лимит: 500MB');
                    continue;
                }

                let isDuplicate = false;
                for (let j = 0; j < uploadedFiles.length; j++) {
                    if (uploadedFiles[j].name === file.name) {
                        isDuplicate = true;
                        break;
                    }
                }

                if (!isDuplicate) {
                    uploadedFiles.push(file);
                }
            }

            input.value = '';
            updateFilesUI();
        });

        function validateForm() {
            const login = document.getElementById('login').value.trim();
            const platform = document.getElementById('platform').value;
            const version = document.getElementById('version').value.trim();
            const errorTime = document.getElementById('error_time').value;
            const server = document.getElementById('server').value;
            const description = document.getElementById('description').value.trim();

            return login && platform && version && errorTime && server && description;
        }

        function updateMainButton() {
            if (currentPage !== 'form') return;

            if (validateForm()) {
                tg.MainButton.setText('Отправить отчёт');
                tg.MainButton.show();
                tg.MainButton.enable();
            } else {
                tg.MainButton.hide();
            }
        }

        document.querySelectorAll('#bug-form input, #bug-form textarea').forEach(el => {
            el.addEventListener('input', updateMainButton);
        });

        function showError(message) {
            const errorEl = document.getElementById('error-message');
            errorEl.textContent = message;
            errorEl.classList.add('show');
            setTimeout(() => errorEl.classList.remove('show'), 5000);
        }

        function showSuccess() {
            document.getElementById('bug-form').style.display = 'none';
            document.getElementById('success-message').classList.add('show');
            tg.MainButton.hide();
        }

        function updateProgress(percent) {
            document.getElementById('progress-bar-fill').style.width = percent + '%';
            document.getElementById('progress-text').textContent = Math.round(percent) + '%';
        }

        function setUploadStage(stage, hint) {
            document.getElementById('upload-stage').textContent = stage;
            document.getElementById('upload-hint').textContent = hint || '';
        }

        function showUploadOverlay() {
            updateProgress(0);
            setUploadStage('Этап 1 из 2: Загрузка на сервер', 'Подготовка файлов...');
            document.getElementById('upload-overlay').classList.add('show');
        }

        function hideUploadOverlay() {
            document.getElementById('upload-overlay').classList.remove('show');
            document.getElementById('progress-bar-fill').classList.remove('pulsing');
            setUploadStage('', '');
        }

        tg.MainButton.onClick(function() {
            if (currentPage !== 'form') return;

            if (!validateForm()) {
                showError('Заполните все обязательные поля');
                return;
            }

            tg.MainButton.showProgress();
            tg.MainButton.disable();

            const formData = new FormData();
            formData.append('login', document.getElementById('login').value.trim());
            formData.append('platform', document.getElementById('platform').value);
            formData.append('version', document.getElementById('version').value.trim());
            formData.append('error_time', document.getElementById('error_time').value);
            formData.append('server', document.getElementById('server').value);
            formData.append('subscriber', document.getElementById('subscriber').value.trim());
            formData.append('description', document.getElementById('description').value.trim());
            formData.append('init_data', tg.initData);

            if (chatId) {
                formData.append('chat_id', chatId);
            }

            uploadedFiles.forEach(function(file) {
                formData.append('media', file);
            });

            if (uploadedFiles.length > 0) {
                showUploadOverlay();
            }

            const xhr = new XMLHttpRequest();

            // Для расчёта скорости загрузки
            let uploadStartTime = Date.now();
            let lastLoaded = 0;
            let lastTime = uploadStartTime;
            let currentSpeed = 0;

            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percent = (e.loaded / e.total) * 100;
                    updateProgress(percent);

                    // Расчёт скорости каждые 0.5 сек
                    const now = Date.now();
                    const timeDiff = (now - lastTime) / 1000;
                    if (timeDiff >= 0.5) {
                        const bytesDiff = e.loaded - lastLoaded;
                        currentSpeed = bytesDiff / timeDiff;
                        lastLoaded = e.loaded;
                        lastTime = now;
                    }

                    // Форматирование скорости
                    let speedText = '';
                    if (currentSpeed > 0) {
                        if (currentSpeed >= 1024 * 1024) {
                            speedText = (currentSpeed / (1024 * 1024)).toFixed(1) + ' MB/s';
                        } else if (currentSpeed >= 1024) {
                            speedText = (currentSpeed / 1024).toFixed(0) + ' KB/s';
                        } else {
                            speedText = currentSpeed.toFixed(0) + ' B/s';
                        }
                    }

                    // Расчёт оставшегося времени
                    let etaText = '';
                    if (currentSpeed > 0 && e.loaded < e.total) {
                        const remaining = e.total - e.loaded;
                        const etaSeconds = Math.round(remaining / currentSpeed);
                        if (etaSeconds >= 60) {
                            const mins = Math.floor(etaSeconds / 60);
                            const secs = etaSeconds % 60;
                            etaText = mins + ' мин ' + secs + ' сек';
                        } else {
                            etaText = etaSeconds + ' сек';
                        }
                    }

                    // Обновление подсказки с прогрессом
                    const loadedMB = (e.loaded / (1024 * 1024)).toFixed(1);
                    const totalMB = (e.total / (1024 * 1024)).toFixed(1);
                    let hint = loadedMB + ' / ' + totalMB + ' MB';
                    if (speedText) hint += ' • ' + speedText;
                    if (etaText) hint += ' • ~' + etaText;
                    setUploadStage('Этап 1 из 2: Загрузка на сервер', hint);

                    // Переход ко 2 этапу (отправка в Telegram)
                    if (e.loaded >= e.total) {
                        setUploadStage('Этап 2 из 2: Отправка в Telegram', 'Это может занять некоторое время для больших файлов...');
                        document.getElementById('progress-bar-fill').classList.add('pulsing');
                        document.getElementById('progress-text').textContent = 'Обработка...';
                    }
                }
            });

            xhr.addEventListener('load', function() {
                hideUploadOverlay();

                if (xhr.status === 200) {
                    try {
                        const result = JSON.parse(xhr.responseText);
                        if (result.success) {
                            showSuccess();
                            setTimeout(function() { tg.close(); }, 1500);
                        } else {
                            throw new Error(result.error || 'Unknown error');
                        }
                    } catch (e) {
                        showError('Ошибка при отправке: ' + e.message);
                        tg.MainButton.hideProgress();
                        tg.MainButton.enable();
                    }
                } else {
                    showError('Ошибка сервера: ' + xhr.status);
                    tg.MainButton.hideProgress();
                    tg.MainButton.enable();
                }
            });

            xhr.addEventListener('error', function() {
                hideUploadOverlay();
                showError('Ошибка сети');
                tg.MainButton.hideProgress();
                tg.MainButton.enable();
            });

            xhr.addEventListener('timeout', function() {
                hideUploadOverlay();
                showError('Превышено время ожидания');
                tg.MainButton.hideProgress();
                tg.MainButton.enable();
            });

            xhr.open('POST', '/api/report');
            xhr.timeout = 300000;
            xhr.send(formData);
        });

        // ==================== МОИ РЕПОРТЫ ====================

        async function loadMyReports(append = false) {
            if (myReportsLoading) return;
            myReportsLoading = true;

            if (!append) {
                myReportsOffset = 0;
                myReports = [];
            }

            try {
                const response = await fetch('/api/user-reports', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        chat_id: chatId,
                        limit: PAGE_SIZE,
                        offset: myReportsOffset
                    })
                });

                const result = await response.json();

                document.getElementById('my-loading').style.display = 'none';
                myReportsLoaded = true;

                if (result.success) {
                    myReports = myReports.concat(result.reports);
                    myReportsHasMore = result.has_more;
                    myReportsOffset += result.reports.length;
                    renderMyReports();

                    // Открытие конкретного репорта по deep link
                    if (openReportId && !append) {
                        const report = myReports.find(r => r.id === openReportId);
                        if (report) {
                            openUserReport(openReportId);
                        }
                        openReportId = null;
                    }
                } else {
                    document.getElementById('my-report-list').innerHTML =
                        `<div class="error-message show">${escapeHtml(result.error || 'Ошибка загрузки')}</div>`;
                }
            } catch (error) {
                document.getElementById('my-loading').style.display = 'none';
                document.getElementById('my-report-list').innerHTML =
                    '<div class="error-message show">Ошибка соединения</div>';
            } finally {
                myReportsLoading = false;
            }
        }

        function renderMyReports() {
            const list = document.getElementById('my-report-list');
            const empty = document.getElementById('my-empty');

            if (myReports.length === 0) {
                empty.style.display = 'block';
                list.innerHTML = '';
                return;
            }

            empty.style.display = 'none';

            let html = myReports.map(report => `
                <div class="report-card" onclick="openUserReport(${report.id})">
                    <div class="report-header">
                        <span class="report-number">Репорт #${report.report_number}</span>
                        <span class="report-status status-${report.status || 'new'}">${statusLabels[report.status] || 'Новая'}</span>
                    </div>
                    <div class="report-info">${escapeHtml(report.platform)}${report.platform_version ? ' ' + escapeHtml(report.platform_version) : ''} • ${escapeHtml(report.server)}</div>
                    <div class="report-info">${formatDate(report.created_at)}</div>
                    <div class="report-description">${escapeHtml(report.description || '')}</div>
                    ${report.tracking_id ? `<div class="tracking-id">ID: ${escapeHtml(report.tracking_id)}</div>` : ''}
                </div>
            `).join('');

            if (myReportsHasMore) {
                html += `<button class="load-more-btn" onclick="loadMyReports(true)">Загрузить ещё</button>`;
            }

            list.innerHTML = html;
        }

        let currentUserPlatform = '';
        let currentUserServer = '';

        // Кнопки выбора платформы в модалке пользователя
        document.querySelectorAll('#user-platform-group .platform-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#user-platform-group .platform-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                currentUserPlatform = btn.dataset.value;
            });
        });

        // Кнопки выбора сервера в модалке пользователя
        document.querySelectorAll('#user-server-group .server-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#user-server-group .server-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                currentUserServer = btn.dataset.value;
            });
        });

        function openUserReport(reportId) {
            currentUserReportId = reportId;
            const report = myReports.find(r => r.id === reportId);
            if (!report) return;

            // Редактирование доступно только для статусов "new" и "revision"
            const isEditable = !report.status || report.status === 'new' || report.status === 'revision';

            document.getElementById('user-modal-title').textContent = `Репорт #${report.report_number}`;
            document.getElementById('user-detail-status').innerHTML =
                `<span class="report-status status-${report.status || 'new'}">${statusLabels[report.status] || 'Новая'}</span>`;

            // Показываем комментарий к доработке
            const commentRow = document.getElementById('user-revision-comment-row');
            if (report.status === 'revision' && report.status_comment) {
                document.getElementById('user-detail-comment').textContent = report.status_comment;
                commentRow.style.display = 'block';
            } else {
                commentRow.style.display = 'none';
            }

            document.getElementById('user-detail-tracking').textContent = report.tracking_id || 'Не назначен';
            document.getElementById('user-detail-login').value = report.user_login || '';
            document.getElementById('user-detail-version').value = report.platform_version || '';
            document.getElementById('user-detail-time').value = report.error_time || '';
            document.getElementById('user-detail-subscriber').value = report.subscriber_info || '';
            document.getElementById('user-detail-description').value = report.description || '';
            document.getElementById('user-detail-created').textContent = formatDate(report.created_at);

            currentUserPlatform = report.platform || '';
            document.querySelectorAll('#user-platform-group .platform-btn').forEach(btn => {
                btn.classList.toggle('selected', btn.dataset.value === currentUserPlatform);
            });

            currentUserServer = report.server || '';
            document.querySelectorAll('#user-server-group .server-btn').forEach(btn => {
                btn.classList.toggle('selected', btn.dataset.value === currentUserServer);
            });

            // Блокировка/разблокировка полей в зависимости от статуса
            const inputFields = [
                'user-detail-login',
                'user-detail-version',
                'user-detail-time',
                'user-detail-subscriber',
                'user-detail-description'
            ];

            inputFields.forEach(id => {
                const el = document.getElementById(id);
                el.disabled = !isEditable;
                el.style.opacity = isEditable ? '1' : '0.6';
            });

            document.querySelectorAll('#user-platform-group .platform-btn').forEach(btn => {
                btn.disabled = !isEditable;
                btn.style.opacity = isEditable ? '1' : '0.6';
                btn.style.pointerEvents = isEditable ? 'auto' : 'none';
            });

            document.querySelectorAll('#user-server-group .server-btn').forEach(btn => {
                btn.disabled = !isEditable;
                btn.style.opacity = isEditable ? '1' : '0.6';
                btn.style.pointerEvents = isEditable ? 'auto' : 'none';
            });

            const saveBtn = document.getElementById('user-save-btn');
            const errorDiv = document.getElementById('user-modal-error');

            if (isEditable) {
                saveBtn.style.display = 'block';
                errorDiv.classList.remove('show');
            } else {
                saveBtn.style.display = 'none';
                errorDiv.textContent = 'Редактирование заблокировано: статус заявки изменён';
                errorDiv.classList.add('show');
                errorDiv.style.backgroundColor = '#fff3e0';
                errorDiv.style.color = '#e65100';
            }

            document.getElementById('user-modal').classList.add('active');
        }

        function closeUserModal() {
            document.getElementById('user-modal').classList.remove('active');
            currentUserReportId = null;

            const errorDiv = document.getElementById('user-modal-error');
            errorDiv.classList.remove('show');
            errorDiv.style.backgroundColor = '';
            errorDiv.style.color = '';
        }

        async function saveUserReport() {
            if (!currentUserReportId) return;

            const btn = document.getElementById('user-save-btn');
            btn.disabled = true;
            btn.textContent = 'Сохранение...';

            try {
                const response = await fetch('/api/update-report', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        report_id: currentUserReportId,
                        user_login: document.getElementById('user-detail-login').value,
                        platform: currentUserPlatform,
                        platform_version: document.getElementById('user-detail-version').value,
                        error_time: document.getElementById('user-detail-time').value,
                        server: currentUserServer,
                        subscriber_info: document.getElementById('user-detail-subscriber').value,
                        description: document.getElementById('user-detail-description').value
                    })
                });

                const result = await response.json();

                if (result.success) {
                    const report = myReports.find(r => r.id === currentUserReportId);
                    if (report) {
                        report.user_login = document.getElementById('user-detail-login').value;
                        report.platform = currentUserPlatform;
                        report.platform_version = document.getElementById('user-detail-version').value;
                        report.error_time = document.getElementById('user-detail-time').value;
                        report.server = currentUserServer;
                        report.subscriber_info = document.getElementById('user-detail-subscriber').value;
                        report.description = document.getElementById('user-detail-description').value;
                    }
                    renderMyReports();
                    closeUserModal();
                    tg.showAlert('Изменения сохранены');
                } else {
                    const errorDiv = document.getElementById('user-modal-error');
                    errorDiv.textContent = result.error || 'Ошибка сохранения';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                const errorDiv = document.getElementById('user-modal-error');
                errorDiv.textContent = 'Ошибка соединения';
                errorDiv.classList.add('show');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Сохранить изменения';
            }
        }

        // ==================== АДМИН-ПАНЕЛЬ ====================

        // Фильтры по статусу
        document.querySelectorAll('#admin-filters .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('#admin-filters .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentAdminFilter = btn.dataset.status;
                loadAdminReports(false);
            });
        });

        async function loadAdminReports(append = false) {
            if (!chatId) return;
            if (adminReportsLoading) return;
            adminReportsLoading = true;

            if (!append) {
                adminReportsOffset = 0;
                adminReports = [];
                document.getElementById('admin-report-list').innerHTML = '<div class="loading">Загрузка...</div>';
            }

            try {
                const requestBody = {
                    init_data: tg.initData,
                    chat_id: chatId,
                    limit: PAGE_SIZE,
                    offset: adminReportsOffset,
                    include_stats: !append
                };
                if (currentAdminFilter) {
                    requestBody.status = currentAdminFilter;
                }

                const response = await fetch('/api/chat-reports', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                const result = await response.json();

                document.getElementById('admin-loading').style.display = 'none';
                adminReportsLoaded = true;

                if (result.success) {
                    adminReports = adminReports.concat(result.reports);
                    adminReportsHasMore = result.has_more;
                    adminReportsOffset += result.reports.length;

                    if (result.stats) {
                        adminStats = result.stats;
                        updateAdminStats();
                    }

                    document.getElementById('admin-toolbar').style.display = 'flex';
                    document.getElementById('admin-filters').style.display = 'flex';
                    document.getElementById('admin-stats').style.display = 'flex';
                    renderAdminReports();

                    // Открытие репорта по admin deep link
                    if (openAsAdmin && openReportId && !append) {
                        const report = adminReports.find(r => r.id === openReportId);
                        if (report) {
                            openAdminReport(openReportId);
                        }
                        openReportId = null;
                        openAsAdmin = false;
                    }
                } else if (response.status === 403) {
                    document.getElementById('admin-report-list').innerHTML =
                        '<div class="empty-state"><div class="empty-state-icon">\uD83D\uDD12</div><p>Доступ запрещён</p></div>';
                } else {
                    document.getElementById('admin-report-list').innerHTML =
                        `<div class="error-message show">${escapeHtml(result.error || 'Ошибка загрузки')}</div>`;
                }
            } catch (error) {
                document.getElementById('admin-loading').style.display = 'none';
                document.getElementById('admin-report-list').innerHTML =
                    '<div class="error-message show">Ошибка соединения</div>';
            } finally {
                adminReportsLoading = false;
            }
        }

        function updateAdminStats() {
            document.getElementById('stat-total').textContent = adminStats.total || 0;
            document.getElementById('stat-open').textContent = adminStats.new || 0;
            document.getElementById('stat-progress').textContent = adminStats.in_progress || 0;
            document.getElementById('stat-resolved').textContent = adminStats.completed || 0;
        }


        function renderAdminReports() {
            const list = document.getElementById('admin-report-list');
            const empty = document.getElementById('admin-empty');

            if (adminReports.length === 0) {
                empty.style.display = 'block';
                list.innerHTML = '';
                return;
            }

            empty.style.display = 'none';

            let html = adminReports.map(report => `
                <div class="report-card" onclick="openAdminReport(${report.id})">
                    <div class="report-header">
                        <span class="report-number">Репорт #${report.report_number}</span>
                        <span class="report-status status-${report.status || 'new'}">${statusLabels[report.status] || 'Новая'}</span>
                    </div>
                    <div class="report-user">@${escapeHtml(report.username || 'unknown')} • ${escapeHtml(report.user_login || '-')}</div>
                    <div class="report-info">${escapeHtml(report.platform)}${report.platform_version ? ' ' + escapeHtml(report.platform_version) : ''} • ${escapeHtml(report.server)}</div>
                    <div class="report-info">${formatDate(report.created_at)}</div>
                    <div class="report-description">${escapeHtml(report.description || '')}</div>
                    ${report.tracking_id ? `<div class="tracking-id">ID: ${escapeHtml(report.tracking_id)}</div>` : ''}
                </div>
            `).join('');

            if (adminReportsHasMore) {
                html += `<button class="load-more-btn" onclick="loadAdminReports(true)">Загрузить ещё</button>`;
            }

            list.innerHTML = html;
        }

        function toggleRevisionComment() {
            const status = document.getElementById('admin-detail-status').value;
            const commentRow = document.getElementById('revision-comment-row');
            commentRow.style.display = status === 'revision' ? 'block' : 'none';
        }

        function openAdminReport(reportId) {
            currentAdminReportId = reportId;
            const report = adminReports.find(r => r.id === reportId);
            if (!report) return;

            document.getElementById('admin-modal-title').textContent = `Репорт #${report.report_number}`;
            document.getElementById('admin-detail-user').textContent = report.username ? `@${report.username}` : 'Неизвестен';
            document.getElementById('admin-detail-status').value = report.status || 'new';
            document.getElementById('admin-detail-tracking').value = report.tracking_id || '';
            document.getElementById('admin-detail-comment').value = report.status_comment || '';
            document.getElementById('admin-detail-login').textContent = report.user_login || '-';
            document.getElementById('admin-detail-platform').textContent = report.platform || '-';
            document.getElementById('admin-detail-version').textContent = report.platform_version || '-';
            document.getElementById('admin-detail-time').textContent = report.error_time || '-';
            document.getElementById('admin-detail-server').textContent = report.server || '-';
            document.getElementById('admin-detail-subscriber').textContent = report.subscriber_info || '-';
            document.getElementById('admin-detail-description').textContent = report.description || '-';
            document.getElementById('admin-detail-created').textContent = formatDate(report.created_at);

            toggleRevisionComment();

            document.getElementById('admin-modal-error').classList.remove('show');
            document.getElementById('admin-modal').classList.add('active');
        }

        function closeAdminModal() {
            document.getElementById('admin-modal').classList.remove('active');
            currentAdminReportId = null;
        }

        async function saveAdminReport() {
            if (!currentAdminReportId) return;

            const btn = document.getElementById('admin-save-btn');
            btn.disabled = true;
            btn.textContent = 'Сохранение...';

            try {
                const newStatus = document.getElementById('admin-detail-status').value;
                const response = await fetch('/api/update-report', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        report_id: currentAdminReportId,
                        status: newStatus,
                        tracking_id: document.getElementById('admin-detail-tracking').value,
                        status_comment: newStatus === 'revision' ? document.getElementById('admin-detail-comment').value : ''
                    })
                });

                const result = await response.json();

                if (result.success) {
                    const report = adminReports.find(r => r.id === currentAdminReportId);
                    if (report) {
                        report.status = newStatus;
                        report.tracking_id = document.getElementById('admin-detail-tracking').value;
                        report.status_comment = newStatus === 'revision' ? document.getElementById('admin-detail-comment').value : '';
                    }
                    closeAdminModal();
                    tg.showAlert('Изменения сохранены');
                    loadAdminReports(false);
                } else {
                    const errorDiv = document.getElementById('admin-modal-error');
                    errorDiv.textContent = result.error || 'Ошибка сохранения';
                    errorDiv.classList.add('show');
                }
            } catch (error) {
                const errorDiv = document.getElementById('admin-modal-error');
                errorDiv.textContent = 'Ошибка соединения';
                errorDiv.classList.add('show');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Сохранить';
            }
        }

        // ==================== ПОИСК И ЭКСПОРТ ====================

        async function searchReports() {
            const query = document.getElementById('admin-search-input').value.trim();
            if (!query) {
                loadAdminReports(false);
                return;
            }

            const list = document.getElementById('admin-report-list');
            list.innerHTML = '<div class="loading">Поиск...</div>';

            try {
                const response = await fetch('/api/search-reports', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        chat_id: chatId,
                        query: query
                    })
                });

                const result = await response.json();

                if (result.success) {
                    adminReports = result.reports;
                    renderAdminReports();
                } else {
                    list.innerHTML = '<div class="error-message show">' + escapeHtml(result.error || 'Ошибка поиска') + '</div>';
                }
            } catch (error) {
                list.innerHTML = '<div class="error-message show">Ошибка соединения</div>';
            }
        }

        async function exportCSV() {
            try {
                const response = await fetch('/api/export-csv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        init_data: tg.initData,
                        chat_id: chatId
                    })
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'reports.csv';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                } else {
                    tg.showAlert('Ошибка экспорта');
                }
            } catch (error) {
                tg.showAlert('Ошибка соединения');
            }
        }

        // Поиск по Enter
        document.getElementById('admin-search-input')?.addEventListener('keyup', function(e) {
            if (e.key === 'Enter') searchReports();
        });

        // ==================== УТИЛИТЫ ====================

        function formatDate(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleDateString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Закрытие модалок по клику на оверлей
        document.getElementById('user-modal').addEventListener('click', function(e) {
            if (e.target === this) closeUserModal();
        });
        document.getElementById('admin-modal').addEventListener('click', function(e) {
            if (e.target === this) closeAdminModal();
        });

        // Инициализация
        checkAdmin();
        updateMainButton();
