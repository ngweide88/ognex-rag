import { Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { AppShell } from "./components/AppShell";
import { ChatPage } from "./pages/ChatPage";
import { KnowledgeBasePage } from "./pages/KnowledgeBasePage";
import { NotFoundPage } from "./pages/NotFoundPage";

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<ChatPage />} />
          <Route path="knowledge-bases" element={<KnowledgeBasePage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ToastProvider>
  );
}