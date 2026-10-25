import { NavLink, Navigate, Outlet, Route, Routes, useSearchParams } from "react-router-dom";
import Accuracy from "./pages/Accuracy";
import Decision from "./pages/Decision";
import { useJson } from "./api";
import { formatStamp } from "./format";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/review" element={<Decision />} />
        <Route path="/accuracy" element={<Accuracy />} />
        <Route path="*" element={<Navigate to="/review" replace />} />
      </Route>
    </Routes>
  );
}

function HomeRedirect() {
  const [params] = useSearchParams();
  const query = params.toString();
  return <Navigate to={query ? `/review?${query}` : "/review"} replace />;
}

function Shell() {
  const meta = useJson("/api/meta");
  const ingested = meta.data?.ingestedAt ? formatStamp(meta.data.ingestedAt) : null;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/review" className="wordmark">
            Day-ahead wind
            <span>GB national · January 2026</span>
          </NavLink>
          <nav className="nav" aria-label="Pages">
            <NavLink to="/review">Review</NavLink>
            <NavLink to="/accuracy">Accuracy</NavLink>
          </nav>
        </div>
      </header>
      <main className="wrap">
        <Outlet />
      </main>
      <footer className="footer">
        <div className="wrap footer-inner">
          <p>
            Sources: Elexon WINDFOR forecast and FUELHH metered wind. The 09:50 London
            cutoff is this desk’s assumption for the day-ahead auction, not a time
            sent by Elexon. A dash in a table is a missing record.
            {ingested ? ` Data saved ${ingested}.` : ""}
          </p>
        </div>
      </footer>
    </>
  );
}
