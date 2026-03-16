# 🚀 Quick Start Guide - The Beast AI Next.js

## Prerequisites
- Node.js 18+ installed ([Download here](https://nodejs.org/))
- FastAPI backend running on `http://localhost:8000`

## Installation & Setup

### Step 1: Navigate to the Next.js app directory
```bash
cd "/Users/wgomaa/Work/TNN/AI Project/The Beast/tnn-beast/poc/nextjs-app"
```

### Step 2: Install dependencies
```bash
npm install
```

This will install:
- Next.js 14 (App Router)
- React 18
- TypeScript
- Tailwind CSS
- Framer Motion (animations)
- Chart.js (charts)
- Lucide React (icons)

### Step 3: Start the development server
```bash
npm run dev
```

The app will start on **http://localhost:3000** 🎉

### Step 4: Open in browser
Navigate to: **http://localhost:3000**

---

## 🎨 What You'll See

### Welcome Screen
- Beautiful onboarding with suggested queries
- 4 quick-start cards with example questions
- Gradient animations

### ChatGPT-Style Interface
- **Left Sidebar**: Quick questions, new chat button, message counter
- **Main Area**: Chat messages with user/AI distinction
- **Bottom Input**: Auto-expanding textarea with send button

### Features in Action
1. **Ask a question** - Type naturally like "Show me top 10 videos"
2. **View results** - See analytics cards with metrics
3. **Export data** - One-click CSV download
4. **Quick questions** - Click sidebar shortcuts

---

## 🔧 Configuration

### API Endpoint
Edit `.env.local` to change the backend URL:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Port Configuration
Edit `package.json` scripts to change the port:
```json
"dev": "next dev -p 3001"  // Changes to port 3001
```

---

## 📦 Project Structure

```
nextjs-app/
├── app/                    # Next.js App Router
│   ├── layout.tsx         # Root layout with fonts
│   ├── page.tsx           # Home page (ChatContainer)
│   └── globals.css        # Global styles & animations
│
├── components/            # React components
│   ├── ChatContainer.tsx  # Main state management
│   ├── Sidebar.tsx        # Navigation & quick questions
│   ├── ChatArea.tsx       # Message list & scroll
│   ├── ChatMessage.tsx    # Individual message display
│   ├── MessageInput.tsx   # Input box with send
│   ├── WelcomeScreen.tsx  # Onboarding screen
│   ├── ResultCard.tsx     # Result display card
│   ├── DashboardStats.tsx # Statistics dashboard
│   └── LoadingSkeleton.tsx # Loading shimmer
│
├── lib/                   # Utilities
│   └── api.ts            # API calls & formatting
│
├── types/                 # TypeScript definitions
│   └── index.ts          # Interfaces & types
│
├── public/               # Static assets
├── next.config.js        # Next.js configuration
├── tailwind.config.js    # Tailwind customization
└── tsconfig.json         # TypeScript config
```

---

## 🎯 Key Features

### 1. ChatGPT-Style UI ✅
- Dark theme (#343541 background)
- Collapsible sidebar
- User vs AI message styling
- Avatar icons (User & Bot)
- Message timestamps
- Smooth scroll to latest message

### 2. Analytics Dashboard ✅
- 4 stat cards (Results, Views, Engagement, Completion)
- Animated number counters
- Gradient backgrounds
- Export to CSV button

### 3. Result Cards ✅
- Platform badges (Facebook, Instagram, etc.)
- 4 key metrics per card
- Gradient metric displays
- Direct links to content
- Hover effects

### 4. Animations ✅
- Framer Motion transitions
- Slide-in messages
- Fade-in components
- Shimmer loading states
- Hover scale effects

### 5. Responsive Design ✅
- Mobile sidebar overlay
- Adaptive grid layouts
- Touch-friendly buttons
- Breakpoints: sm (640px), lg (1024px)

---

## 🚀 Development Commands

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Start production server
npm start

# Run linter
npm run lint
```

---

## 🎨 Customization

### Change Colors
Edit `tailwind.config.js`:
```js
theme: {
  extend: {
    colors: {
      'chat-bg': '#343541',        // Main background
      'sidebar-bg': '#202123',      // Sidebar background
      'message-user': '#343541',    // User message
      'message-assistant': '#444654' // AI message
    }
  }
}
```

### Add More Quick Questions
Edit `components/Sidebar.tsx`:
```typescript
const quickQuestions = [
  { id: 6, text: 'Your new question', icon: '🎯' },
]
```

### Modify Gradients
All gradients use Tailwind classes:
- `from-blue-500 to-purple-600` - Blue to purple
- `from-pink-500 to-rose-500` - Pink to rose
- `from-green-500 to-emerald-500` - Green to emerald

---

## 📱 Mobile Experience

The app is fully responsive:
- **Mobile (<640px)**: Sidebar becomes overlay with toggle button
- **Tablet (640-1024px)**: Adjusted grid layouts
- **Desktop (>1024px)**: Full sidebar visible

---

## 🔗 API Integration

The app calls your FastAPI backend:

**Endpoint**: `POST http://localhost:8000/search/query`

**Request**:
```json
{
  "question": "Show me top 10 videos",
  "top_k": 10
}
```

**Response**:
```json
{
  "question": "...",
  "count": 10,
  "results": [...]
}
```

---

## 🐛 Troubleshooting

### Port 3000 already in use?
```bash
# Find and kill the process
lsof -ti:3000 | xargs kill -9

# Or use a different port
npm run dev -- -p 3001
```

### Backend not responding?
Check that FastAPI is running:
```bash
# Should see: Running on http://localhost:8000
curl http://localhost:8000/health
```

### Module not found errors?
Reinstall dependencies:
```bash
rm -rf node_modules package-lock.json
npm install
```

---

## ✨ What's Different from Flask Version?

### Next.js Advantages:
- ⚡ **Faster**: React virtual DOM, client-side navigation
- 🎨 **Better animations**: Framer Motion integration
- 📦 **Component reusability**: Modular React components
- 🔄 **Real-time updates**: No page refreshes
- 📱 **Superior mobile**: React Native-like experience
- 🎯 **Type safety**: Full TypeScript support
- 🚀 **Production ready**: Built-in optimization

### Key Improvements:
1. **Smoother animations** - Framer Motion vs CSS only
2. **Better state management** - React hooks vs jQuery-style
3. **Component isolation** - Each piece is self-contained
4. **Type safety** - TypeScript catches errors before runtime
5. **Modern development** - Hot reload, fast refresh
6. **SEO friendly** - Server-side rendering support

---

## 📚 Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [React Documentation](https://react.dev)
- [Tailwind CSS](https://tailwindcss.com)
- [Framer Motion](https://www.framer.com/motion/)

---

**Built with ❤️ using Next.js + React + Tailwind CSS**

Enjoy your modern ChatGPT-style analytics dashboard! 🎉
