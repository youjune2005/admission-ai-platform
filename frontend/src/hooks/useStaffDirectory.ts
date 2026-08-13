import { useCallback, useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { StaffPerson } from "../lib/archiveWizard";

export function useStaffDirectory() {
  const [staffList, setStaffList] = useState<StaffPerson[]>([]);

  const loadStaff = useCallback(async () => {
    const res = await apiClient.get<StaffPerson[]>("/api/staff");
    setStaffList(res.data);
  }, []);

  useEffect(() => {
    loadStaff().catch(() => setStaffList([]));
  }, [loadStaff]);

  const saveStaffName = useCallback(async (raw: string) => {
    const name = raw.trim();
    if (!name) return null;
    const res = await apiClient.post<StaffPerson>("/api/staff", { name });
    setStaffList((prev) => {
      if (prev.some((p) => p.id === res.data.id || p.name === res.data.name)) {
        return prev.map((p) => (p.id === res.data.id ? res.data : p));
      }
      return [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name, "ko"));
    });
    return res.data;
  }, []);

  const deleteStaff = useCallback(async (id: number) => {
    await apiClient.delete(`/api/staff/${id}`);
    setStaffList((prev) => prev.filter((p) => p.id !== id));
  }, []);

  return { staffList, loadStaff, saveStaffName, deleteStaff };
}
