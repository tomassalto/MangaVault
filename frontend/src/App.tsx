import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Library } from "./pages/Library";
import { MangaDetail } from "./pages/MangaDetail";
import { Reader } from "./pages/Reader";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Library />} />
          <Route path="/manga/:slug" element={<MangaDetail />} />
        </Route>
        {/* Reader is fullscreen, no layout */}
        <Route path="/read/:slug/:chapter" element={<Reader />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
