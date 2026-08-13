import { useLocation, Outlet } from "react-router-dom";

/** 라우트 전환 시 부드러운 페이지 진입 애니메이션 */
export default function PageTransition() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="page-enter h-full min-h-0 phone:h-auto phone:min-h-full">
      <Outlet />
    </div>
  );
}
