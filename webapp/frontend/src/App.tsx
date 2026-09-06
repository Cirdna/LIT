import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import Portfolio from "./routes/Portfolio";
import DocumentDetail from "./routes/DocumentDetail";
import Calendar from "./routes/Calendar";
import Conflicts from "./routes/Conflicts";
import HandoffBrief from "./routes/HandoffBrief";
import Scope from "./routes/Scope";
import Chat from "./routes/Chat";
import StatuteReview from "./routes/StatuteReview";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Portfolio />} />
        <Route path="/documents/:id" element={<DocumentDetail />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/conflicts" element={<Conflicts />} />
        <Route path="/statutes" element={<StatuteReview />} />
        <Route path="/handoffs/:id" element={<HandoffBrief />} />
        <Route path="/scope" element={<Scope />} />
      </Routes>
    </Layout>
  );
}
