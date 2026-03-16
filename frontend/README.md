# The Beast AI - Next.js App

Modern ChatGPT-style analytics dashboard built with Next.js, React, and Tailwind CSS.

## 🚀 Tech Stack

- **Next.js 14** - App Router with Server Components
- **React 18** - UI library
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first styling
- **Framer Motion** - Smooth animations
- **Chart.js** - Data visualization
- **Lucide React** - Beautiful icons

## 📦 Installation

```bash
cd nextjs-app
npm install
```

## 🏃 Running the App

```bash
# Development mode
npm run dev

# Production build
npm run build
npm start
```

The app will be available at: **http://localhost:3000**

## 🎨 Features

### ChatGPT-Style Interface
- **Collapsible Sidebar**: Quick questions and navigation
- **Chat Messages**: User and AI messages with distinct styling
- **Welcome Screen**: Beautiful onboarding with suggested queries
- **Smooth Animations**: Framer Motion transitions

### Analytics Dashboard
- **Real-time Stats**: Total results, views, engagement, completion rate
- **Result Cards**: Beautiful cards with metrics and gradients
- **Export to CSV**: One-click data export
- **Loading States**: Shimmer skeleton screens

### Responsive Design
- Mobile-first approach
- Sidebar overlay on mobile
- Adaptive grid layouts
- Touch-friendly interactions

## 📁 Project Structure

```
nextjs-app/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Home page
│   └── globals.css         # Global styles
├── components/
│   ├── ChatContainer.tsx   # Main container
│   ├── Sidebar.tsx         # Navigation sidebar
│   ├── ChatArea.tsx        # Chat messages area
│   ├── ChatMessage.tsx     # Individual message
│   ├── MessageInput.tsx    # Input box
│   ├── WelcomeScreen.tsx   # Onboarding screen
│   ├── ResultCard.tsx      # Result display card
│   ├── DashboardStats.tsx  # Statistics dashboard
│   └── LoadingSkeleton.tsx # Loading state
├── lib/
│   └── api.ts              # API integration
├── types/
│   └── index.ts            # TypeScript types
├── public/                 # Static assets
├── next.config.js          # Next.js config
├── tailwind.config.js      # Tailwind config
└── tsconfig.json           # TypeScript config
```

## 🔧 Environment Variables

Create `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 🎯 Key Components

### ChatContainer
Main orchestrator managing state and message flow.

### Sidebar
- Quick question shortcuts
- New chat button
- Message counter
- Responsive with mobile overlay

### ChatArea
- Message list with auto-scroll
- Welcome screen for new chats
- Loading states
- Quick question integration

### MessageInput
- Auto-expanding textarea
- Send on Enter (Shift+Enter for new line)
- Disabled during loading
- Smooth submit animation

### ResultCard
- Gradient borders and backgrounds
- Metric grid with icons
- Platform badges
- Direct links to content

### DashboardStats
- Animated stat cards
- Total results, views, engagement
- Average completion rate
- CSV export button

## 🎨 Design System

### Colors
```
Background: #343541 (ChatGPT dark)
Sidebar: #202123 (Darker sidebar)
Message User: #343541
Message Assistant: #444654
Accent: Blue to Purple gradient
```

### Animations
- Slide-in for messages
- Fade-in for components
- Hover effects on cards
- Shimmer loading states

## 🌐 API Integration

The app connects to your FastAPI backend at `http://localhost:8000`.

### Endpoint Used
- `POST /search/query` - Query content with natural language

### API Service
Located in `lib/api.ts` with functions:
- `queryContent()` - Send questions to backend
- `formatNumber()` - Format numbers (1.2K, 3.5M)
- `formatDate()` - Format dates
- `exportToCSV()` - Export results to CSV

## 📱 Responsive Breakpoints

- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

## ⚡ Performance

- Server-side rendering (SSR)
- Automatic code splitting
- Optimized images and fonts
- Lazy loading components
- Efficient re-renders

## 🎭 ChatGPT-Style Features

✅ Dark theme with proper contrast
✅ Collapsible sidebar
✅ User vs AI message styling
✅ Avatar icons (User & Bot)
✅ Timestamp on messages
✅ Loading states with dots
✅ Smooth scrolling
✅ Auto-expanding input
✅ Quick suggestions
✅ Welcome screen

---

**Built with ❤️ for The Beast AI**
