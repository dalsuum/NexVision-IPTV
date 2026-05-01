  'use strict';

  // ═══════════════════════════════════════════════════════════════════════════
  // CAF context
  // ═══════════════════════════════════════════════════════════════════════════

  const context       = cast.framework.CastReceiverContext.getInstance();
  const playerManager = context.getPlayerManager();   // correct v3 accessor

  // ═══════════════════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════════════════

  let hlsInstance  = null;   // current Hls instance, or null
  let _infoTimer   = null;   // handle for info-bar auto-hide
  let _errorTimer  = null;   // handle for error-overlay auto-hide

  // How long (ms) the channel info bar stays visible after a LOAD.
  const INFO_SHOW_MS = 5000;

  // ═══════════════════════════════════════════════════════════════════════════
  // DOM helpers
  // ═══════════════════════════════════════════════════════════════════════════

  const $  = id => document.getElementById(id);

  function showSpinner(on) {
    $('nv-spinner').classList.toggle('show', on);
  }

  function showInfoBar(on) {
    clearTimeout(_infoTimer);
    $('nv-info').classList.toggle('show', on);
    if (on) {
      _infoTimer = setTimeout(() => $('nv-info').classList.remove('show'), INFO_SHOW_MS);
    }
  }

  function showError(msg) {
    showSpinner(false);
    $('nv-error-msg').textContent = msg || 'Stream unavailable';
    $('nv-error').classList.add('show');
    clearTimeout(_errorTimer);
    _errorTimer = setTimeout(() => $('nv-error').classList.remove('show'), 8000);
  }

  // Populate the info bar from the CAF MediaInformation object.
  function populateInfoBar(media) {
    if (!media) return;

    // Title: prefer metadata.title, fall back to contentId
    const title =
      (media.metadata && media.metadata.title) ||
      media.contentId ||
      '—';
    $('nv-channel-name').textContent = title;

    // EPG description
    const subtitle = (media.metadata && media.metadata.subtitle) || '';
    $('nv-subtitle').textContent = subtitle;

    // Logo image
    const logoEl = $('nv-logo');
    const imgs   = media.metadata && media.metadata.images;
    if (imgs && imgs.length > 0 && imgs[0].url) {
      logoEl.src           = imgs[0].url;
      logoEl.style.display = 'block';
      logoEl.onerror       = () => { logoEl.style.display = 'none'; };
    } else {
      logoEl.style.display = 'none';
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Shadow-DOM video accessor
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // <cast-media-player> renders its <video> element inside a shadow root.
  // Accessing that element lets HLS.js attach directly via MediaSource
  // Extensions, taking full control of buffering and segment fetching while
  // the framework continues to read currentTime / duration / paused for its
  // sender-facing status broadcasts.
  //
  function getCastVideoEl() {
    const cmp = document.querySelector('cast-media-player');
    if (!cmp || !cmp.shadowRoot) return null;
    return cmp.shadowRoot.querySelector('video');
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HLS.js engine
  // ═══════════════════════════════════════════════════════════════════════════

  function destroyHls() {
    if (hlsInstance) {
      hlsInstance.destroy();
      hlsInstance = null;
    }
  }

  // attachHls() is called via setTimeout(0) from the LOAD interceptor so
  // that CAF's synchronous default handler runs first and has the video
  // element ready in the shadow DOM before we take it over.
  function attachHls(url) {
    const video = getCastVideoEl();

    if (!video) {
      // Shadow DOM not accessible — the framework will handle HLS natively
      // on Chromecast (Chrome MSE supports application/x-mpegurl directly).
      showSpinner(false);
      return;
    }

    destroyHls();

    // Safari / environments where MSE is unavailable — fall back to native.
    if (!Hls.isSupported()) {
      video.src = url;
      video.play().catch(() => {});
      showSpinner(false);
      return;
    }

    // ── Configure HLS.js for live IPTV streams ────────────────────────────
    hlsInstance = new Hls({
      enableWorker:               true,
      lowLatencyMode:             true,   // target edge of live window
      maxBufferLength:            30,     // seconds of forward buffer
      maxMaxBufferLength:         60,
      liveSyncDurationCount:      3,      // segments behind live edge
      liveMaxLatencyDurationCount: 6,
      maxLoadingDelay:            4,
      manifestLoadingTimeOut:     10000,  // 10 s manifest timeout
      fragLoadingTimeOut:         20000,  // 20 s segment timeout
      // Retry transient network errors before declaring fatal
      manifestLoadingMaxRetry:    3,
      fragLoadingMaxRetry:        4,
    });

    hlsInstance.loadSource(url);

    // attachMedia() replaces whatever src the framework set on the video
    // element with a blob: MediaSource URL — HLS.js owns the pipeline from
    // this point on.
    hlsInstance.attachMedia(video);

    // ── Event handlers ────────────────────────────────────────────────────

    hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play().catch(() => {});
      showSpinner(false);
    });

    hlsInstance.on(Hls.Events.ERROR, (_event, data) => {
      if (!data.fatal) return;   // non-fatal: HLS.js self-recovers

      switch (data.type) {
        case Hls.ErrorTypes.NETWORK_ERROR:
          // Transient network hiccup — ask HLS.js to re-try from where it left off.
          try { hlsInstance.startLoad(); } catch (_) {}
          break;

        case Hls.ErrorTypes.MEDIA_ERROR:
          // Codec / decode error — attempt in-place media recovery.
          try { hlsInstance.recoverMediaError(); } catch (_) {}
          break;

        default:
          // Unrecoverable: destroy instance and surface error to the viewer.
          destroyHls();
          showError('Stream error — ' + (data.details || 'unknown'));
          break;
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // LOAD message interceptor
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Runs before the framework's default LOAD handler.  We:
  //   1. Auto-detect HLS content type when the sender omits it
  //   2. Update the NexVision overlay immediately (before first frame)
  //   3. Schedule HLS.js attachment on the next tick so the framework can
  //      process its synchronous setup first
  //
  playerManager.setMessageInterceptor(
    cast.framework.messages.MessageType.LOAD,
    request => {
      if (!request || !request.media) return request;

      const url = (request.media.contentUrl || request.media.contentId || '').trim();

      // ── Content-type sniffing ────────────────────────────────────────────
      if (!request.media.contentType) {
        if (/\.m3u8($|\?)|\/hls\/|\/live\//i.test(url)) {
          request.media.contentType = 'application/x-mpegurl';
        } else if (/\.ts($|\?)/i.test(url)) {
          request.media.contentType = 'video/mp2t';
        }
      }

      // ── Overlay update ───────────────────────────────────────────────────
      $('nv-error').classList.remove('show');
      populateInfoBar(request.media);
      showInfoBar(true);
      showSpinner(true);

      // ── HLS.js takeover (deferred) ───────────────────────────────────────
      // setTimeout(0) yields control back to the CAF default handler which
      // sets up the shadow-DOM <video> element, then our callback runs and
      // calls attachMedia() to hand the MSE pipeline to HLS.js.
      setTimeout(() => attachHls(url), 0);

      return request;
    }
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // Player state events
  // ═══════════════════════════════════════════════════════════════════════════

  // BUFFERING fires when the video element stalls waiting for data and when
  // it resumes — keeps the spinner in sync with actual playback health.
  playerManager.addEventListener(
    cast.framework.events.EventType.BUFFERING,
    e => showSpinner(e.isBuffering)
  );

  // PLAYER_LOAD_COMPLETE fires on the video element's 'canplay' event.
  // Hide the spinner in case HLS.js MANIFEST_PARSED didn't already do so.
  playerManager.addEventListener(
    cast.framework.events.EventType.PLAYER_LOAD_COMPLETE,
    () => showSpinner(false)
  );

  // Clean up HLS.js when the sender ends / replaces the media session.
  playerManager.addEventListener(
    cast.framework.events.EventType.MEDIA_FINISHED,
    () => {
      destroyHls();
      showSpinner(false);
      showInfoBar(false);
    }
  );

  // ═══════════════════════════════════════════════════════════════════════════
  // Start receiver
  // ═══════════════════════════════════════════════════════════════════════════

  const options         = new cast.framework.CastReceiverOptions();
  options.maxInactivity = 600;   // disconnect idle devices after 10 minutes

  context.start(options);
