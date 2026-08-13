/** 핸드폰만 true. 아이패드·안드로이드 태블릿·PC는 false. */

export function detectIsPhone(): boolean {
  if (typeof window === "undefined") return false;

  const ua = navigator.userAgent || "";
  const isIpad =
    /iPad/i.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (isIpad) return false;

  // Android 태블릿은 보통 "Mobile"이 없음
  if (/Android/i.test(ua) && !/Mobile/i.test(ua)) return false;

  if (/iPhone|iPod|Android.+Mobile|webOS|BlackBerry|IEMobile|Opera Mini/i.test(ua)) {
    return true;
  }

  // UA가 없는 좁은 창(개발자도구 등)도 세로 UI
  return window.matchMedia("(max-width: 767px)").matches;
}

export function syncDeviceDataset(isPhone: boolean) {
  document.documentElement.dataset.device = isPhone ? "phone" : "desktop";
}
