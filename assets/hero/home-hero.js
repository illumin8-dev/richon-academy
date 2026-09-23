
    (() => {
      const scrollSection = document.getElementById('heroScroll');
      const heroLight = document.getElementById('heroLight');
      const heroDim = document.getElementById('heroDim');
      const switchGlow = document.getElementById('switchGlow');
      const scrollGuide = document.getElementById('scrollGuide');
      const siteNav = document.getElementById('siteNav');
      
      
      const copyOff = document.getElementById('copyOff');
      const copyOn = document.getElementById('copyOn');
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
      const mobileMq = window.matchMedia('(max-width: 768px)');

      document.documentElement.classList.add('hero-js');
      let ticking = false;

      const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
      const range = (value, start, end) => clamp((value - start) / (end - start));
      const smoothstep = t => t * t * (3 - 2 * t);

      function render() {
        ticking = false;
        if (reduceMotion.matches) return;

        const rect = scrollSection.getBoundingClientRect();
        const maxScroll = Math.max(1, scrollSection.offsetHeight - document.getElementById('heroSticky').offsetHeight);
        const progress = clamp(-rect.top / maxScroll);

        const mobile = mobileMq.matches;
        const timing = mobile ? {
          guideEnd: 0.14,
          navStart: 0.86,
          navEnd: 0.97,
          lightStart: 0.34,
          lightEnd: 0.60,
          dimEnd: 0.64,
          glowStart: 0.24,
          glowPeak: 0.38,
          glowOutStart: 0.48,
          glowOutEnd: 0.70,
          offStart: 0.40,
          offEnd: 0.54,
          onStart: 0.56,
          onEnd: 0.72
        } : {
          guideEnd: 0.16,
          navStart: 0.88,
          navEnd: 0.98,
          lightStart: 0.40,
          lightEnd: 0.68,
          dimEnd: 0.70,
          glowStart: 0.28,
          glowPeak: 0.43,
          glowOutStart: 0.52,
          glowOutEnd: 0.78,
          offStart: 0.46,
          offEnd: 0.60,
          onStart: 0.62,
          onEnd: 0.78
        };

        // 첫 진입 안내는 초반에만 보이고 바로 사라진다.
        const guideOut = smoothstep(range(progress, 0.02, timing.guideEnd));
        scrollGuide.style.opacity = String(1 - guideOut);
        scrollGuide.style.transform = `translate(-50%, ${guideOut * 8}px)`;

        // ON 화면을 충분히 보여준 뒤 기존 헤더가 뒤늦게 등장한다.
        const navIn = smoothstep(range(progress, timing.navStart, timing.navEnd));
        siteNav.style.opacity = String(navIn);
        siteNav.style.transform = `translateY(${-16 * (1 - navIn)}px)`;
        siteNav.style.visibility = navIn > 0.01 ? 'visible' : 'hidden';
        siteNav.style.pointerEvents = navIn > 0.8 ? 'auto' : 'none';

        // 화면 전체 노출이 부드럽게 올라간다.
        const lightIn = smoothstep(range(progress, timing.lightStart, timing.lightEnd));
        heroLight.style.opacity = String(lightIn);

        const dimOut = smoothstep(range(progress, timing.lightStart, timing.dimEnd));
        heroDim.style.opacity = String(0.88 * (1 - dimOut));

        // 스위치 주변의 넓은 온기만 먼저 생긴다.
        const glowIn = smoothstep(range(progress, timing.glowStart, timing.glowPeak));
        const glowOut = smoothstep(range(progress, timing.glowOutStart, timing.glowOutEnd));
        const glowOpacity = glowIn * (1 - 0.72 * glowOut);
        switchGlow.style.opacity = String(glowOpacity * 0.78);
        switchGlow.style.transform = `translate(-50%, -50%) scale(${0.72 + glowIn * 0.28})`;

        const offOut = smoothstep(range(progress, timing.offStart, timing.offEnd));
        copyOff.style.opacity = String(1 - offOut);
        copyOff.style.transform = `translateY(${-8 * offOut}px)`;

        const onIn = smoothstep(range(progress, timing.onStart, timing.onEnd));
        copyOn.style.opacity = String(onIn);
        copyOn.style.transform = `translateY(${18 * (1 - onIn)}px)`;
      }

      function requestRender() {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(render);
        }
      }

      window.addEventListener('scroll', requestRender, { passive: true });
      window.addEventListener('resize', requestRender);
      reduceMotion.addEventListener?.('change', requestRender);
      mobileMq.addEventListener?.('change', requestRender);

      render();
    })();
  