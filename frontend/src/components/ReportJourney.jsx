import { useEffect, useRef, useState } from "react";

/** Scroll Craft flow patterns adapted to a working report, without scroll hijacking. */
export default function ReportJourney({ sections, children }) {
  const root = useRef(null);
  const nav = useRef(null);
  const [active, setActive] = useState(sections[0]?.id);

  useEffect(() => {
    const container = root.current;
    const targets = sections.map(({ id }) => container.querySelector(`#${id}`)).filter(Boolean);
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const animations = new Set();
    let frame = 0;
    const update = () => {
      frame = 0;
      const edge = nav.current.getBoundingClientRect().bottom + 16;
      let current = targets[0];
      targets.forEach((target) => {
        if (target.getBoundingClientRect().top <= edge) current = target;
      });
      if (current) setActive(current.id);
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    const observer = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        if (!isIntersecting) return;
        observer.unobserve(target);
        if (!motion.matches && target.animate) {
          const animation = target.animate([
            { transform: "translateY(8px)" }, { transform: "translateY(0)" },
          ], { duration: 240, easing: "ease-out" });
          animations.add(animation);
          animation.onfinish = () => animations.delete(animation);
        }
      });
    }, { threshold: 0.08 }) : null;
    targets.forEach((target) => observer?.observe(target));
    const stopMotion = () => {
      if (motion.matches) {
        animations.forEach((animation) => animation.cancel());
        animations.clear();
      }
    };
    motion.addEventListener("change", stopMotion);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    update();
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      motion.removeEventListener("change", stopMotion);
      observer?.disconnect();
      animations.forEach((animation) => animation.cancel());
    };
  }, [sections]);

  const jump = (event, id) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = root.current.querySelector(`#${id}`);
    if (!target) return;
    event.preventDefault();
    target.focus({ preventScroll: true });
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduced ? "instant" : "smooth", block: "start" });
    setActive(id);
  };

  return <div ref={root} className="cv-report-journey">
    <nav ref={nav} aria-label="Recovery report sections" className="cv-report-nav">
      {sections.map(({ id, label }) => <a key={id} href={`#${id}`} onClick={(event) => jump(event, id)}
        aria-current={active === id ? "location" : undefined}>{label}</a>)}
    </nav>
    {children}
  </div>;
}
