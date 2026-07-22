export const metadata = {
  title: "IIS Web Monitor",
  description: "IIS 요청 로그 기반 장애/응답지연 모니터링",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body
        style={{
          margin: 0,
          fontFamily:
            "'Segoe UI', system-ui, -apple-system, Roboto, 'Apple SD Gothic Neo', sans-serif",
          background: "#0b1220",
          color: "#e6edf3",
          minHeight: "100vh",
        }}
      >
        {children}
      </body>
    </html>
  );
}
