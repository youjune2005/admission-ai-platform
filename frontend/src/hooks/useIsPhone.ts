import { useEffect, useState } from "react";
import { detectIsPhone, syncDeviceDataset } from "../lib/device";

export function useIsPhone() {
  const [isPhone, setIsPhone] = useState(() => detectIsPhone());

  useEffect(() => {
    const apply = () => {
      const next = detectIsPhone();
      setIsPhone(next);
      syncDeviceDataset(next);
    };
    apply();
    const mq = window.matchMedia("(max-width: 767px)");
    mq.addEventListener("change", apply);
    window.addEventListener("orientationchange", apply);
    return () => {
      mq.removeEventListener("change", apply);
      window.removeEventListener("orientationchange", apply);
    };
  }, []);

  return isPhone;
}
