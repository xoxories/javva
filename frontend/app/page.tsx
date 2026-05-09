import { ChatContainer } from "@/components/chat/ChatContainer";

export default function Home() {
  return (
    <main
      className="min-h-screen"
      style={{ backgroundColor: "var(--javva-bg)" }}
    >
      <ChatContainer />
    </main>
  );
}
