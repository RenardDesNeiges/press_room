(function () {
  const player = document.querySelector('.audio-player');
  if (player) {
    const audio = player.querySelector('audio');
    const button = player.querySelector('.audio-play-button');
    const timeDisplay = player.querySelector('.audio-time');
    if (audio && button) {
      function formatTime(seconds) {
        if (!isFinite(seconds) || isNaN(seconds)) return '0:00';
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return minutes + ':' + (secs < 10 ? '0' : '') + secs;
      }

      function updateTime() {
        if (timeDisplay) {
          timeDisplay.textContent = formatTime(audio.currentTime) + ' / ' + formatTime(audio.duration);
        }
      }

      button.addEventListener('click', function () {
        if (audio.paused) {
          audio.play();
        } else {
          audio.pause();
        }
      });

      function setPlaying(isPlaying) {
        button.classList.toggle('is-playing', isPlaying);
        button.textContent = isPlaying ? '❚❚ Pause' : '▶ Écouter l\'édito';
      }

      audio.addEventListener('play', function () { setPlaying(true); });
      audio.addEventListener('pause', function () { setPlaying(false); });
      audio.addEventListener('ended', function () { setPlaying(false); });

      audio.addEventListener('timeupdate', updateTime);
      audio.addEventListener('loadedmetadata', updateTime);
      audio.addEventListener('durationchange', updateTime);
    }
  }
})();

(function () {
  const fills = document.querySelectorAll('.stats-bar-fill.anim');
  if (fills.length && ('IntersectionObserver' in window)) {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.style.width = entry.target.getAttribute('data-width') + '%';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.3 });
    fills.forEach(function (fill) { observer.observe(fill); });
  }
})();

(function () {
  const titleLink = document.querySelector('.headline-link');
  const editorial = document.getElementById('editorial');
  if (titleLink && editorial) {
    titleLink.addEventListener('click', function (event) {
      event.preventDefault();
      const topBar = document.querySelector('.top-bar');
      const offset = topBar ? topBar.offsetHeight + 16 : 0;
      const target = editorial.getBoundingClientRect().top + window.pageYOffset - offset;
      window.scrollTo({ top: target, behavior: 'smooth' });
      history.replaceState(null, '', '#editorial');
    });
  }
})();

(function () {
  const tags = document.querySelectorAll('.article-tag');
  if (!tags.length) return;
  const grid = document.querySelector('.article-grid');
  const main = grid ? grid.parentNode : document.body;
  const topBar = document.querySelector('.top-bar');

  const banner = document.createElement('div');
  banner.className = 'filter-banner';
  banner.hidden = true;
  banner.innerHTML =
    '<h2 class="filter-banner-title"></h2>' +
    '<button type="button" class="filter-banner-clear">cliquer pour mettre fin au filtre</button>';
  if (grid) main.insertBefore(banner, grid);

  function normalize(s) {
    return (s || '').toLowerCase().trim();
  }

  function scrollToBanner() {
    const offset = topBar ? topBar.offsetHeight + 16 : 0;
    const target = banner.getBoundingClientRect().top + window.pageYOffset - offset;
    window.scrollTo({ top: target, behavior: 'smooth' });
  }

  function activateTag(value) {
    clearFilter();
    tags.forEach(function (tag) {
      if (normalize(tag.getAttribute('data-tag-value')) === normalize(value)) {
        tag.classList.add('is-active');
      }
    });
    applyFilter(value, value);
    scrollToBanner();
  }

  function activateSource(sourceKey, label) {
    clearFilter();
    applyFilter(sourceKey, label);
    scrollToBanner();
  }

  function applyFilter(needleRaw, display) {
    const needle = normalize(needleRaw);
    document.querySelectorAll('.article-grid .grid-item').forEach(function (item) {
      const article = item.querySelector('.article');
      let match = article && article.querySelectorAll('.article-tag').length
        && Array.prototype.some.call(
          article.querySelectorAll('.article-tag'),
          function (tag) { return normalize(tag.getAttribute('data-tag-value')) === needle; }
        );
      if (article && !match && normalize(article.getAttribute('data-source')) === needle) {
        match = true;
      }
      const media = item.querySelector('.grid-media');
      if (media) {
        match = match || Array.prototype.some.call(
          (media.getAttribute('data-tags') || '').split(/\s+/),
          function (tag) { return normalize(tag) === needle; }
        );
      }
      item.classList.toggle('is-filtered', !match);
    });
    if (grid) grid.classList.add('is-filtering');
    banner.querySelector('.filter-banner-title').textContent = display || needleRaw;
    banner.hidden = false;
  }

  function clearFilter() {
    document.querySelectorAll('.is-filtered').forEach(function (el) {
      el.classList.remove('is-filtered');
    });
    tags.forEach(function (tag) { tag.classList.remove('is-active'); });
    if (grid) grid.classList.remove('is-filtering');
    banner.hidden = true;
  }

  tags.forEach(function (tag) {
    tag.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (tag.classList.contains('is-active')) {
        clearFilter();
        return;
      }
      activateTag(tag.getAttribute('data-tag-value'));
    });
  });

  document.querySelectorAll('.stats-bar-link').forEach(function (link) {
    link.addEventListener('click', function (event) {
      event.preventDefault();
      const label = link.textContent.trim();
      const sourceKey = link.getAttribute('data-scroll-source');
      if (sourceKey) {
        activateSource(sourceKey, label);
        return;
      }
      activateTag(label);
    });
  });

  banner.querySelector('.filter-banner-clear').addEventListener('click', function () {
    clearFilter();
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') clearFilter();
  });
})();

(function () {
  const picker = document.querySelector('.day-picker');
  if (!picker) return;
  const button = picker.querySelector('.top-bar-date');
  const menu = picker.querySelector('.day-menu');
  if (!button || !menu) return;

  function setOpen(open) {
    menu.hidden = !open;
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  button.addEventListener('click', function (event) {
    event.stopPropagation();
    setOpen(menu.hidden);
  });

  document.addEventListener('click', function () {
    setOpen(false);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') setOpen(false);
  });
})();

(function () {
  const hamburger = document.querySelector('.hamburger');
  const right = document.querySelector('.top-bar-right');
  if (!hamburger || !right) return;

  function setOpen(open) {
    right.classList.toggle('is-open', open);
    hamburger.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  hamburger.addEventListener('click', function (event) {
    event.stopPropagation();
    setOpen(!right.classList.contains('is-open'));
  });

  document.addEventListener('click', function (event) {
    if (!right.contains(event.target) && !hamburger.contains(event.target)) {
      setOpen(false);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') setOpen(false);
  });
})();

(function () {
  const form = document.getElementById('feeds-form');
  if (!form) return;
  const container = document.getElementById('publications');
  const jsonField = document.getElementById('feeds-json');
  const addPubButton = document.getElementById('add-pub');

  function addFeedRow(feedsBlock, value) {
    const row = document.createElement('div');
    row.className = 'feed-row';
    row.innerHTML =
      '<input type="url" class="feed-url">' +
      '<button type="button" class="feed-row-remove" aria-label="Retirer ce flux">×</button>';
    if (value) row.querySelector('.feed-url').value = value;
    feedsBlock.appendChild(row);
  }

  function addPublication(pub) {
    pub = pub || {};
    const fieldset = document.createElement('fieldset');
    fieldset.className = 'publication';
    fieldset.innerHTML =
      '<div class="pub-fields">' +
      '<label>Nom <input type="text" class="pub-name"></label>' +
      '<label class="pub-lang-label">Langue <input type="text" class="pub-lang"></label>' +
      '<label class="pub-today-label"><input type="checkbox" class="pub-today"> Aujourd\'hui uniquement</label>' +
      '</div>' +
      '<div class="pub-feeds"></div>' +
      '<div class="pub-actions">' +
      '<button type="button" class="add-feed">Ajouter un flux</button>' +
      '<button type="button" class="remove-pub">Supprimer</button>' +
      '</div>';
    fieldset.querySelector('.pub-name').value = pub.name || '';
    fieldset.querySelector('.pub-lang').value = pub.lang || '';
    fieldset.querySelector('.pub-today').checked = !!(pub.today_only);
    const feedsBlock = fieldset.querySelector('.pub-feeds');
    (pub.feeds && pub.feeds.length ? pub.feeds : ['']).forEach(function (url) {
      addFeedRow(feedsBlock, url);
    });
    container.appendChild(fieldset);
  }

  container.addEventListener('click', function (event) {
    const target = event.target;
    if (target.classList.contains('add-feed')) {
      addFeedRow(target.closest('.publication').querySelector('.pub-feeds'), '');
    } else if (target.classList.contains('remove-pub')) {
      target.closest('.publication').remove();
    } else if (target.classList.contains('feed-row-remove')) {
      target.closest('.feed-row').remove();
    }
  });

  if (addPubButton) {
    addPubButton.addEventListener('click', function () {
      addPublication();
    });
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    const publications = [];
    container.querySelectorAll('.publication').forEach(function (fieldset) {
      const name = fieldset.querySelector('.pub-name').value.trim();
      if (!name) return;
      const feeds = [];
      fieldset.querySelectorAll('.feed-url').forEach(function (input) {
        const url = input.value.trim();
        if (url) feeds.push(url);
      });
      publications.push({
        name: name,
        lang: fieldset.querySelector('.pub-lang').value.trim(),
        feeds: feeds,
        today_only: fieldset.querySelector('.pub-today').checked
      });
    });
    jsonField.value = JSON.stringify(publications);
    form.submit();
  });
})();

(function () {
  const slider = document.getElementById('editorial-minutes');
  const display = document.getElementById('editorial-minutes-value');
  if (!slider || !display) return;
  slider.addEventListener('input', function () {
    display.textContent = slider.value + ' min';
  });
})();

(function () {
  // Lightweight live reload: reload the page if press_room.html changes.
  let lastModified = null;
  const checkInterval = 30000; // 30 seconds

  async function checkForUpdate() {
    try {
      const response = await fetch("press_room.html", { method: "HEAD", cache: "no-store" });
      const modified = response.headers.get("Last-Modified");
      if (lastModified && modified && lastModified !== modified) {
        location.reload();
      }
      lastModified = modified || lastModified;
    } catch (err) {
      // Ignore network errors; retry on the next interval.
    }
  }

  checkForUpdate();
  setInterval(checkForUpdate, checkInterval);
})();

(function () {
  // Collapsible JSON tree viewer for the news_summary admin stage.
  // No-op on every page that lacks the data contract.
  const dataScript = document.getElementById('news-summary-tree-data');
  const container = document.getElementById('news-summary-tree');
  if (!dataScript || !container) return;

  let data;
  try {
    data = JSON.parse(dataScript.textContent);
  } catch (err) {
    return;
  }

  const collapsedClass = 'is-collapsed';
  const hiddenClass = 'is-hidden';
  const matchClass = 'is-match';

  const input = document.getElementById('tree-search');
  const expandBtn = document.getElementById('tree-expand-all');
  const collapseBtn = document.getElementById('tree-collapse-all');

  const allRecords = [];
  let matchCount = 0;
  let rootRecord = null;

  function el(tag, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function normText(s) {
    return String(s == null ? '' : s).toLowerCase();
  }

  // JSONPath segments (used by copy): identifier keys -> /key, other keys -> .key, array index -> [i].
  function segmentForKey(key) {
    return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(key) ? '/' + key : '.' + key;
  }

  function isEmptyContainer(value) {
    if (value === null || typeof value !== 'object') return false;
    if (Array.isArray(value)) return value.length === 0;
    return Object.keys(value).length === 0;
  }

  function defaultCollapsedKey(key) {
    if (key === null || key === undefined) return false;
    const k = String(key).toLowerCase();
    return k === 'facts' || k === 'views';
  }

  function buildNode(keyText, searchKey, value, path, isRoot) {
    // Skip the always-single "Topics" wrapper under a region.
    let disp = value;
    if (!Array.isArray(disp) && disp !== null && typeof disp === 'object') {
      const keys = Object.keys(disp);
      if (keys.length === 1 && keys[0] === 'Topics') disp = disp['Topics'];
    }
    const isObject = disp !== null && typeof disp === 'object';
    const isEmptyCont = isEmptyContainer(disp);
    const isBranch = isObject && !isEmptyCont;

    const row = el('div', isBranch ? 'tree-row' : 'tree-row tree-leaf');
    if (!isRoot && keyText === '' && !isBranch) row.classList.add('bare-row');
    row.setAttribute('data-path', path);
    if (isBranch) row.setAttribute('aria-expanded', 'true');

    const toggle = el('span', isBranch ? 'tree-toggle' : 'tree-toggle is-empty');
    toggle.textContent = isBranch ? '▼' : '';
    if (isBranch) toggle.setAttribute('data-action', 'toggle');
    row.appendChild(toggle);

    const keySpan = el('span', 'tree-key tok-key');
    keySpan.textContent = keyText;
    row.appendChild(keySpan);

    if (!isRoot) {
      const colon = el('span', 'tree-colon');
      colon.textContent = ':';
      row.appendChild(colon);
    }

    const record = {
      el: row,
      branch: isBranch,
      children: [],
      group: null,
      keyName: String(searchKey || ''),
      search: normText(isRoot ? '$' : searchKey)
    };
    row._tree = record;
    allRecords.push(record);

    if (isBranch) {
      const group = el('div', 'tree-children');
      const inner = el('div', 'tree-branch-inner');
      group.appendChild(inner);
      record.group = group;

      if (Array.isArray(disp)) {
        // Render array members without `[i]` index rows. Object members have
        // their own keys promoted as direct children (`[{FR: {...}}]` becomes
        // `FR` under the array key), while scalar members become bare-value
        // leaf rows. The real array index is still kept in `data-path` so
        // copied JSONPath stays exact.
        for (let i = 0; i < disp.length; i++) {
          const item = disp[i];
          const itemIsObj = item !== null && typeof item === 'object' && !Array.isArray(item);
          if (itemIsObj) {
            const itemPath = path + '[' + i + ']';
            Object.keys(item).forEach(function (k) {
              const child = buildNode(JSON.stringify(k), k, item[k], itemPath + segmentForKey(k), false);
              inner.appendChild(child.el);
              if (child.group) inner.appendChild(child.group);
              record.children.push(child);
            });
          } else {
            const child = buildNode('', String(i), item, path + '[' + i + ']', false);
            inner.appendChild(child.el);
            if (child.group) inner.appendChild(child.group);
            record.children.push(child);
          }
        }
      } else {
        Object.keys(disp).forEach(function (k) {
          const child = buildNode(JSON.stringify(k), k, disp[k], path + segmentForKey(k), false);
          inner.appendChild(child.el);
          if (child.group) inner.appendChild(child.group);
          record.children.push(child);
        });
      }
    } else {
      let valueText;
      let tokenClass;
      if (isEmptyCont) {
        valueText = '(vide)';
        tokenClass = 'tok-empty';
      } else if (disp === null) {
        valueText = 'null';
        tokenClass = 'tok-null';
      } else if (typeof disp === 'boolean') {
        valueText = disp ? 'true' : 'false';
        tokenClass = 'tok-bool';
      } else if (typeof disp === 'number') {
        valueText = String(disp);
        tokenClass = 'tok-number';
      } else {
        valueText = JSON.stringify(String(disp));
        tokenClass = 'tok-string';
      }
      const valueSpan = el('span', 'tree-value ' + tokenClass);
      valueSpan.textContent = valueText;
      row.appendChild(valueSpan);
      record.search += '\n' + normText(isEmptyCont ? '(vide)' : (disp === null ? 'null' : String(disp)));
    }

    return record;
  }

  rootRecord = buildNode('$', 'root', data, '$', true);
  container.appendChild(rootRecord.el);
  if (rootRecord.group) container.appendChild(rootRecord.group);

  function setCollapsed(record, collapsed) {
    const row = record.el;
    row.classList.toggle(collapsedClass, collapsed);
    row.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    if (record.branch) {
      const toggle = row.querySelector('.tree-toggle');
      if (toggle) toggle.textContent = collapsed ? '▶' : '▼';
    }
  }

  allRecords.forEach(function (record) {
    if (record.branch && defaultCollapsedKey(record.keyName)) setCollapsed(record, true);
  });

  container.addEventListener('click', function (event) {
    const target = event.target;
    if (!target || !target.closest) return;

    const toggleBtn = target.closest('.tree-toggle[data-action="toggle"]');
    if (toggleBtn && container.contains(toggleBtn)) {
      const row = toggleBtn.closest('.tree-row');
      if (row && row._tree) {
        setCollapsed(row._tree, !row.classList.contains(collapsedClass));
      }
      return;
    }

    const row = target.closest('.tree-row');
    if (row && container.contains(row)) {
      event.preventDefault();
      copyPath(row, event.clientX, event.clientY);
    }
  });

  function execCopyFallback(text, done) {
    const ta = el('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '0';
    ta.style.left = '0';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
    } catch (err) {
      // Ignore: environment refuses programmatic copy.
    }
    document.body.removeChild(ta);
    if (done) done();
  }

  let tipEl = null;
  let tipTimer = null;

  function ensureTip() {
    if (!tipEl) {
      tipEl = el('div', 'tree-copied-tip');
      tipEl.textContent = 'Copié !';
      container.appendChild(tipEl);
    }
    return tipEl;
  }

  function showTip(clientX, clientY) {
    const tip = ensureTip();
    const rect = container.getBoundingClientRect();
    tip.style.left = (clientX - rect.left + 10) + 'px';
    tip.style.top = (clientY - rect.top + 8) + 'px';
    window.clearTimeout(tipTimer);
    requestAnimationFrame(function () {
      tip.classList.add('is-visible');
    });
    tipTimer = window.setTimeout(function () {
      tip.classList.remove('is-visible');
    }, 1500);
  }

  function copyPath(row, clientX, clientY) {
    const path = row.getAttribute('data-path') || '';
    const onDone = function () { showTip(clientX, clientY); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(path).then(onDone, function () {
        execCopyFallback(path, onDone);
      });
    } else {
      execCopyFallback(path, onDone);
    }
  }

  function updateCount() {
    if (!input || !countEl) return;
    const q = normText(input.value);
    if (!q) {
      countEl.textContent = '';
      return;
    }
    countEl.textContent = matchCount === 0
      ? 'Aucun résultat'
      : (matchCount + (matchCount > 1 ? ' correspondances' : ' correspondance'));
  }

  let countEl = null;
  if (input) {
    countEl = el('span', 'tree-match-count');
    input.insertAdjacentElement('afterend', countEl);
    input.addEventListener('input', function () {
      filterTree(input.value);
    });
  }

  function filterTree(query) {
    const q = normText(query);

    if (!q) {
      allRecords.forEach(function (record) {
        record.el.classList.remove(hiddenClass);
        record.el.classList.remove(matchClass);
        if (record.branch) setCollapsed(record, defaultCollapsedKey(record.keyName));
      });
      matchCount = 0;
      updateCount();
      return;
    }

    matchCount = 0;

    function visit(record) {
      const selfMatch = record.search.indexOf(q) !== -1;
      let childMatch = false;
      if (record.children && record.children.length) {
        record.children.forEach(function (child) {
          if (visit(child)) childMatch = true;
        });
      }
      const visible = selfMatch || childMatch;
      record.el.classList.toggle(hiddenClass, !visible);
      record.el.classList.toggle(matchClass, selfMatch);
      if (selfMatch) matchCount++;
      if (visible && record.branch) setCollapsed(record, false);
      return visible;
    }

    visit(rootRecord);
    updateCount();
  }

  if (expandBtn) {
    expandBtn.addEventListener('click', function () {
      allRecords.forEach(function (record) {
        if (record.branch) setCollapsed(record, false);
      });
    });
  }

  if (collapseBtn) {
    collapseBtn.addEventListener('click', function () {
      allRecords.forEach(function (record) {
        setCollapsed(record, true);
      });
    });
  }
})();
