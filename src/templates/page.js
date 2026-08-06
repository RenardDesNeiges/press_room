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
      '</div>' +
      '<div class="pub-feeds"></div>' +
      '<div class="pub-actions">' +
      '<button type="button" class="add-feed">Ajouter un flux</button>' +
      '<button type="button" class="remove-pub">Supprimer</button>' +
      '</div>';
    fieldset.querySelector('.pub-name').value = pub.name || '';
    fieldset.querySelector('.pub-lang').value = pub.lang || '';
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
        feeds: feeds
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
