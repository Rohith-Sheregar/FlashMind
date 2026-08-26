import './style.css'

// Base URL for all API calls.
// In dev: empty string → Vite proxy forwards /api/* to localhost:5000.
// In production: set VITE_API_URL=https://your-backend.onrender.com in your host env.
const API_URL = import.meta.env.VITE_API_URL || ''

mermaid.initialize({ startOnLoad: false, theme: 'dark' })

let isLoginMode = true
let currentRecordId = null
let currentFlashcards = []

const authScreen = document.getElementById('authScreen')
const mainApp = document.getElementById('mainApp')
const authForm = document.getElementById('authForm')
const authToggleBtn = document.getElementById('authToggleBtn')
const authSubmitBtn = document.getElementById('authSubmitBtn')
const authError = document.getElementById('authError')
const welcomeText = document.getElementById('welcomeText')
const logoutBtn = document.getElementById('logoutBtn')
const deckList = document.getElementById('deckList')

const otpForm = document.getElementById('otpForm')
const otpInput = document.getElementById('otpInput')
const otpEmailDisplay = document.getElementById('otpEmailDisplay')
const otpTimer = document.getElementById('otpTimer')
const resendOtpBtn = document.getElementById('resendOtpBtn')
const backToRegister = document.getElementById('backToRegister')
const emailGroup = document.getElementById('emailGroup')
const emailInput = document.getElementById('email')
const emailFeedback = document.getElementById('emailFeedback')

const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/

let pendingEmail = ''
let otpCountdown = null

// Track remaining credits globally so callAI can guard before firing
let _creditsRemaining = null

async function fetchUserStatus() {
    try {
        const token = localStorage.getItem('token')
        const res = await fetch(`${API_URL}/api/status`, {
            headers: { 'Authorization': 'Bearer ' + token }
        })
        if (res.ok) {
            const data = await res.json()
            const limit = data.limit || 5
            const used = data.generations_used || 0
            const remaining = Math.max(limit - used, 0)
            _creditsRemaining = remaining
            const statsEl = document.getElementById('usageStats')
            statsEl.style.display = 'inline-block'
            statsEl.innerHTML = `Credits: <span id="usageCount">${remaining}</span>/${limit}`
            statsEl.style.color = remaining === 0 ? 'var(--danger)' : remaining <= 1 ? '#f59e0b' : 'var(--accent)'
            // Disable / re-enable all AI generate buttons based on credit status
            const aiButtons = ['generateFlashcardsBtn', 'generateTopicsBtn', 'generateQuizBtn', 'generateMindmapBtn']
            aiButtons.forEach(id => {
                const btn = document.getElementById(id)
                if (!btn) return
                if (remaining === 0) {
                    btn.disabled = true
                    btn.title = 'No credits left. Resets tomorrow.'
                } else {
                    btn.disabled = false
                    btn.title = ''
                }
            })
        }
    } catch (e) {
        console.error('Failed to fetch user status:', e)
    }
}

function checkAuth() {
    const token = localStorage.getItem('token')
    const username = localStorage.getItem('username')
    if (token && username) {
        authScreen.style.display = 'none'
        mainApp.style.display = 'flex'
        welcomeText.textContent = `Welcome, ${username}`
        loadDecks()
        fetchUserStatus()
    } else {
        authScreen.style.display = 'flex'
        mainApp.style.display = 'none'
    }
}
checkAuth()

emailInput.addEventListener('input', () => {
    const val = emailInput.value.trim()
    if (!val) {
        emailFeedback.textContent = ''
        emailFeedback.className = 'input-feedback'
        return
    }
    if (EMAIL_REGEX.test(val)) {
        emailFeedback.textContent = '✓ Valid email'
        emailFeedback.className = 'input-feedback valid'
    } else {
        emailFeedback.textContent = '✗ Invalid email format'
        emailFeedback.className = 'input-feedback invalid'
    }
})

otpInput.addEventListener('input', () => {
    otpInput.value = otpInput.value.replace(/[^0-9]/g, '')
})

authToggleBtn.onclick = () => {
    isLoginMode = !isLoginMode
    authSubmitBtn.textContent = isLoginMode ? 'Login' : 'Register'
    authToggleBtn.textContent = isLoginMode ? "Don't have an account? Register here" : "Already have an account? Login here"
    emailGroup.style.display = isLoginMode ? 'none' : 'block'
    authError.style.display = 'none'
    emailFeedback.textContent = ''
}

function startOtpTimer(seconds) {
    clearInterval(otpCountdown)
    let remaining = seconds
    resendOtpBtn.disabled = true
    resendOtpBtn.style.opacity = '0.5'
    otpTimer.textContent = `Code expires in ${Math.floor(remaining / 60)}:${(remaining % 60).toString().padStart(2, '0')}`
    otpCountdown = setInterval(() => {
        remaining--
        if (remaining <= 0) {
            clearInterval(otpCountdown)
            otpTimer.textContent = 'Code expired'
            resendOtpBtn.disabled = false
            resendOtpBtn.style.opacity = '1'
            return
        }
        otpTimer.textContent = `Code expires in ${Math.floor(remaining / 60)}:${(remaining % 60).toString().padStart(2, '0')}`
    }, 1000)
}

function showOtpPhase(email) {
    pendingEmail = email
    authForm.style.display = 'none'
    authToggleBtn.style.display = 'none'
    otpForm.style.display = 'block'
    otpEmailDisplay.textContent = email
    otpInput.value = ''
    otpInput.focus()
    authError.style.display = 'none'
    startOtpTimer(300)
}

function showRegisterPhase() {
    clearInterval(otpCountdown)
    authForm.style.display = 'block'
    authToggleBtn.style.display = 'block'
    otpForm.style.display = 'none'
    authError.style.display = 'none'
}

backToRegister.onclick = showRegisterPhase

authForm.onsubmit = async (e) => {
    e.preventDefault()
    const user = document.getElementById('username').value.trim()
    const pass = document.getElementById('password').value
    authError.style.display = 'none'

    if (isLoginMode) {
        authSubmitBtn.disabled = true
        authSubmitBtn.textContent = 'Signing in…'
        authSubmitBtn.style.opacity = '0.7'
        try {
            const res = await fetch(`${API_URL}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            })
            const data = await res.json()
            if (res.ok) {
                authSubmitBtn.textContent = '✓ Welcome back!'
                localStorage.setItem('token', data.access_token)
                localStorage.setItem('username', data.username)
                setTimeout(() => checkAuth(), 400)
            } else if (res.status === 401) {
                authError.textContent = '❌ Incorrect username or password.'
                authError.style.display = 'block'
            } else if (res.status === 429) {
                authError.textContent = '⏳ Too many login attempts. Please wait a moment.'
                authError.style.display = 'block'
            } else {
                authError.textContent = data.error || 'Login failed. Please try again.'
                authError.style.display = 'block'
            }
        } catch {
            authError.textContent = '🚫 Network error. Check your connection and try again.'
            authError.style.display = 'block'
        } finally {
            authSubmitBtn.disabled = false
            authSubmitBtn.textContent = 'Login'
            authSubmitBtn.style.opacity = '1'
        }
    } else {
        const email = emailInput.value.trim()
        if (user.length < 3) {
            authError.textContent = 'Username must be at least 3 characters'
            authError.style.display = 'block'
            return
        }
        if (!EMAIL_REGEX.test(email)) {
            authError.textContent = 'Please enter a valid email address'
            authError.style.display = 'block'
            return
        }
        if (pass.length < 6) {
            authError.textContent = 'Password must be at least 6 characters'
            authError.style.display = 'block'
            return
        }
        authSubmitBtn.disabled = true
        authSubmitBtn.textContent = 'Sending OTP…'
        authSubmitBtn.style.opacity = '0.7'
        try {
            const res = await fetch(`${API_URL}/api/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, email, password: pass })
            })
            const data = await res.json()
            if (res.ok) {
                showOtpPhase(email)
            } else if (res.status === 400) {
                authError.textContent = data.error || 'Registration failed. Check your details.'
                authError.style.display = 'block'
            } else if (res.status === 429) {
                authError.textContent = '⏳ Too many requests. Please wait a moment.'
                authError.style.display = 'block'
            } else {
                authError.textContent = data.error || 'Registration failed. Please try again.'
                authError.style.display = 'block'
            }
        } catch {
            authError.textContent = '🚫 Network error. Check your connection and try again.'
            authError.style.display = 'block'
        } finally {
            authSubmitBtn.disabled = false
            authSubmitBtn.textContent = isLoginMode ? 'Login' : 'Register'
            authSubmitBtn.style.opacity = '1'
        }
    }
}

otpForm.onsubmit = async (e) => {
    e.preventDefault()
    const otp = otpInput.value.trim()
    if (otp.length !== 6) {
        authError.textContent = 'Please enter the 6-digit code'
        authError.style.display = 'block'
        return
    }
    const verifyBtn = document.getElementById('verifyOtpBtn')
    verifyBtn.disabled = true
    verifyBtn.textContent = 'Verifying...'
    try {
        const res = await fetch(`${API_URL}/api/verify-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: pendingEmail, otp })
        })
        const data = await res.json()
        if (res.ok) {
            clearInterval(otpCountdown)
            alert('🎉 ' + data.message + ' Please login now.')
            showRegisterPhase()
            isLoginMode = true
            authSubmitBtn.textContent = 'Login'
            authToggleBtn.textContent = "Don't have an account? Register here"
            emailGroup.style.display = 'none'
        } else {
            authError.textContent = data.error || 'Verification failed'
            authError.style.display = 'block'
        }
    } catch {
        authError.textContent = 'Network error'
        authError.style.display = 'block'
    } finally {
        verifyBtn.disabled = false
        verifyBtn.textContent = 'Verify & Create Account'
    }
}

resendOtpBtn.onclick = async () => {
    resendOtpBtn.disabled = true
    resendOtpBtn.textContent = 'Sending...'
    authError.style.display = 'none'
    try {
        const res = await fetch(`${API_URL}/api/resend-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: pendingEmail })
        })
        const data = await res.json()
        if (res.ok) {
            startOtpTimer(300)
            otpInput.value = ''
            otpInput.focus()
        } else {
            authError.textContent = data.error || 'Failed to resend'
            authError.style.display = 'block'
        }
    } catch {
        authError.textContent = 'Network error'
        authError.style.display = 'block'
    } finally {
        resendOtpBtn.textContent = 'Resend OTP'
    }
}

logoutBtn.onclick = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    checkAuth()
}

async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('token')
    if (!options.headers) options.headers = {}
    options.headers['Authorization'] = `Bearer ${token}`
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000)
    options.signal = controller.signal
    try {
        const res = await fetch(url, options)
        clearTimeout(timeoutId)
        if (res.status === 401) {
            alert('Session expired. Please login again.')
            logoutBtn.click()
            throw new Error('Unauthorized')
        }
        return res
    } catch (e) {
        clearTimeout(timeoutId)
        throw e
    }
}

async function fetchWithRetry(url, options = {}, maxRetries = 10, delayMs = 5000) {
    let lastError
    for (let i = 0; i < maxRetries; i++) {
        try {
            if (!navigator.onLine) throw new Error('You are offline.')
            const res = await fetchWithAuth(url, options)
            // Never retry client errors (4xx) — they won't change on retry
            if (!res.ok && res.status < 500) return res
            if (!res.ok && res.status >= 500) {
                const errText = await res.text()
                throw new Error(`Server Error: ${res.status} ${errText}`)
            }
            return res
        } catch (e) {
            lastError = e
            console.warn(`Fetch attempt ${i + 1} failed:`, e)
            if (i < maxRetries - 1) {
                const pText = document.getElementById('generationMessage')
                if (pText && document.getElementById('generationOverlay').style.display !== 'none') {
                    let msg = pText.textContent
                    if (msg.includes('(Retrying')) {
                        msg = msg.replace(/\(Retrying.*\)/, `(Retrying ${i + 1}/${maxRetries})`)
                    } else {
                        msg = `${msg} (Retrying ${i + 1}/${maxRetries})`
                    }
                    pText.textContent = msg
                }
                await new Promise(resolve => setTimeout(resolve, delayMs))
            }
        }
    }
    throw new Error(`The system is currently offline or overloaded. Please try again later. (Failed after ${maxRetries} attempts)`)
}

async function loadDecks(autoSelectLatest = false, _retryCount = 0) {
    const MAX_RETRIES = 2
    const RETRY_DELAY = 2000
    try {
        const res = await fetchWithAuth(`${API_URL}/api/list-generated`)
        let data
        try { data = await res.json() } catch { data = [] }

        if (!res.ok) {
            if (_retryCount < MAX_RETRIES) {
                await new Promise(r => setTimeout(r, RETRY_DELAY))
                return loadDecks(autoSelectLatest, _retryCount + 1)
            }
            deckList.innerHTML = `<div style="padding: 1rem; text-align: center;"><p style="color: var(--danger); margin-bottom: 0.75rem;">Failed to load documents.</p><button class="btn" style="padding: 0.5rem 1rem; font-size: 0.85rem;" onclick="loadDecks()">Retry</button></div>`
            return
        }

        const records = Array.isArray(data) ? data : (Array.isArray(data.records) ? data.records : [])
        deckList.innerHTML = ''
        if (records.length === 0) {
            deckList.innerHTML = '<p class="empty-state" style="padding:0">No documents yet.</p>'
            return
        }

        let latestDiv = null
        records.forEach((record, idx) => {
            const div = document.createElement('div')
            div.className = 'deck-item'
            div.style.position = 'relative'
            div.innerHTML = `
                <div class="deck-title" style="padding-right: 20px;">${record.source_file}</div>
                <div class="deck-meta">${record.flashcards ? record.flashcards.length : 0} cards • ${new Date(record.created_at).toLocaleDateString()}</div>
                <button class="delete-doc-btn" onclick="deleteDocument(event, '${record._id}')" title="Delete Document">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            `
            div.onclick = () => selectDeck(record, div)
            deckList.appendChild(div)
            if (idx === 0) latestDiv = div
        })

        if (autoSelectLatest && latestDiv) latestDiv.click()
    } catch (e) {
        console.error('loadDecks failed:', e)
        if (_retryCount < MAX_RETRIES) {
            await new Promise(r => setTimeout(r, RETRY_DELAY))
            return loadDecks(autoSelectLatest, _retryCount + 1)
        }
        deckList.innerHTML = `<div style="padding: 1rem; text-align: center;"><p style="color: var(--danger); margin-bottom: 0.75rem;">Network error loading documents.</p><button class="btn" style="padding: 0.5rem 1rem; font-size: 0.85rem;" onclick="loadDecks()">Retry</button></div>`
    }
}

window.deleteDocument = async function(event, recordId) {
    event.stopPropagation()
    if (!confirm('Are you sure you want to delete this document? This cannot be undone.')) return
    try {
        const res = await fetchWithAuth(`${API_URL}/api/documents/${recordId}`, { method: 'DELETE' })
        if (res.ok) {
            if (currentRecordId === recordId) {
                document.getElementById('flashcardsEmpty').style.display = 'block'
                document.getElementById('topicsContent').style.display = 'none'
                document.getElementById('quizEmpty').style.display = 'block'
                document.getElementById('quizContent').style.display = 'none'
                document.getElementById('mindmapEmpty').style.display = 'block'
                document.getElementById('mindmapContent').style.display = 'none'
                document.getElementById('flashcardsContainer').innerHTML = ''
            }
            loadDecks()
        } else {
            alert('Failed to delete document.')
        }
    } catch (e) {
        console.error(e)
        alert('Network error while deleting document.')
    }
}

function selectDeck(record, element) {
    document.querySelectorAll('.deck-item').forEach(el => el.classList.remove('active'))
    element.classList.add('active')
    currentRecordId = record._id
    currentFlashcards = record.flashcards

    document.getElementById('flashcardsEmpty').style.display = 'none'
    document.getElementById('topicsEmpty').style.display = 'none'
    document.getElementById('topicsContent').style.display = 'block'
    document.getElementById('quizEmpty').style.display = 'none'
    document.getElementById('quizContent').style.display = 'block'
    document.getElementById('mindmapEmpty').style.display = 'none'
    document.getElementById('mindmapContent').style.display = 'block'

    document.getElementById('topicsResult').innerHTML = ''
    document.getElementById('quizResult').innerHTML = ''
    document.getElementById('mindmapResult').innerHTML = ''

    const btnTopics = document.getElementById('generateTopicsBtn')
    const btnQuiz = document.getElementById('generateQuizBtn')
    const btnMindmap = document.getElementById('generateMindmapBtn')
    const btnFlashcards = document.getElementById('generateFlashcardsBtn')

    btnTopics.style.display = 'block'
    btnQuiz.style.display = 'block'
    btnMindmap.style.display = 'block'
    btnFlashcards.style.display = 'block'

    if (record.topics) { renderTopics(record.topics); btnTopics.textContent = 'Regenerate Topics' }
    else { btnTopics.textContent = 'Generate Topics' }

    if (record.quiz && record.quiz.length > 0) { renderQuiz(record.quiz); btnQuiz.textContent = 'Regenerate Quiz' }
    else { btnQuiz.textContent = 'Generate Quiz' }

    if (record.mindmap) { renderMindmap(record.mindmap); btnMindmap.textContent = 'Regenerate Mind Map' }
    else { btnMindmap.textContent = 'Generate Mind Map' }

    if (record.flashcards && record.flashcards.length > 0) { btnFlashcards.textContent = 'Regenerate Flashcards' }
    else { btnFlashcards.textContent = 'Generate Flashcards' }

    renderFlashcards()

    if (window.innerWidth <= 768) closeMobileSidebar()
}

function renderFlashcards() {
    const container = document.getElementById('flashcardsContainer')
    container.innerHTML = ''
    const btn = document.getElementById('generateFlashcardsBtn')
    btn.style.display = 'block'
    if (!currentFlashcards || currentFlashcards.length === 0) {
        btn.textContent = 'Generate Flashcards'
        return
    }
    btn.textContent = 'Regenerate Flashcards'
    currentFlashcards.forEach((card, index) => {
        const wrapper = document.createElement('div')
        wrapper.className = 'flashcard-wrapper'
        wrapper.innerHTML = `
            <div class="flashcard" onclick="this.classList.toggle('is-flipped')">
                <div class="flashcard-face">
                    <button class="play-btn" onclick="event.stopPropagation(); playVoice(this, ${index})">▶</button>
                    <h3 style="margin-bottom:0.5rem; color:var(--primary);">Q:</h3>
                    <p>${card.question}</p>
                </div>
                <div class="flashcard-face flashcard-back">
                    <h3 style="margin-bottom:0.5rem; color:var(--success);">A:</h3>
                    <p>${card.answer}</p>
                </div>
            </div>
        `
        container.appendChild(wrapper)
    })
}

window.playVoice = function(btn, index) {
    const card = currentFlashcards[index]
    const el = btn.closest('.flashcard')
    window.speechSynthesis.cancel()
    const uFront = new SpeechSynthesisUtterance(card.question)
    const uBack = new SpeechSynthesisUtterance(card.answer)
    el.classList.remove('is-flipped')
    uFront.onend = () => {
        el.classList.add('is-flipped')
        setTimeout(() => window.speechSynthesis.speak(uBack), 500)
    }
    window.speechSynthesis.speak(uFront)
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'))
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'))
        btn.classList.add('active')
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active')
    }
})

window.checkAnswer = function(qIdx, optIdx, correctIdx) {
    const qDiv = document.getElementById(`q-${qIdx}`)
    const options = qDiv.querySelectorAll('.quiz-option')
    options.forEach(opt => {
        opt.style.pointerEvents = 'none'
        opt.classList.remove('correct', 'wrong')
    })
    if (optIdx === correctIdx) {
        options[optIdx].classList.add('correct')
    } else {
        options[optIdx].classList.add('wrong')
        options[correctIdx].classList.add('correct')
    }
    document.getElementById(`exp-${qIdx}`).style.display = 'block'
}

const uploadBox = document.getElementById('uploadBox')
const fileInput = document.getElementById('fileInput')
uploadBox.onclick = () => fileInput.click()

fileInput.onchange = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const formData = new FormData()
    for (let i = 0; i < files.length; i++) formData.append('files', files[i])

    uploadBox.style.pointerEvents = 'none'
    uploadBox.style.opacity = '0.5'
    document.getElementById('uploadSpinner').style.display = 'inline-block'

    const uploadText = uploadBox.querySelector('p')
    const origText = uploadText ? uploadText.textContent : ''
    if (uploadText) uploadText.textContent = `Uploading ${files.length} file${files.length > 1 ? 's' : ''}...`

    try {
        const res = await fetchWithAuth(`${API_URL}/api/upload`, { method: 'POST', body: formData })
        if (res.ok) {
            await loadDecks(true)
            if (window.innerWidth <= 768) closeMobileSidebar()
        } else {
            const data = await res.json()
            alert('Upload failed: ' + (data.error || 'Unknown error'))
        }
    } catch {
        alert('Upload failed. Please try again.')
    } finally {
        uploadBox.style.pointerEvents = 'auto'
        uploadBox.style.opacity = '1'
        document.getElementById('uploadSpinner').style.display = 'none'
        if (uploadText) uploadText.textContent = origText
        fileInput.value = ''
    }
}

function closeMobileSidebar() {
    const sidebar = document.querySelector('.sidebar')
    const backdrop = document.querySelector('.sidebar-backdrop')
    if (sidebar) sidebar.classList.remove('active')
    if (backdrop) backdrop.classList.remove('active')
}

const mobileMenuBtn = document.getElementById('mobileMenuBtn')
if (mobileMenuBtn) {
    const backdrop = document.createElement('div')
    backdrop.className = 'sidebar-backdrop'
    document.body.appendChild(backdrop)

    function toggleSidebar() {
        const sidebar = document.querySelector('.sidebar')
        const isOpen = sidebar.classList.toggle('active')
        backdrop.classList.toggle('active', isOpen)
    }
    mobileMenuBtn.onclick = toggleSidebar
    backdrop.onclick = closeMobileSidebar
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMobileSidebar() })
}

async function callAI(endpoint, actionType, onSuccess, force = false) {
    if (!currentRecordId) return alert('Select a document first')
    if (_creditsRemaining !== null && _creditsRemaining <= 0) {
        return alert('⚠️ You have used all your credits for today. Come back tomorrow!')
    }
    startGenerationOverlay(`Generating ${actionType}...`)
    let progress = 5
    setGenerationProgress(progress, `Generating ${actionType}...`)
    const progressInterval = setInterval(() => {
        if (progress < 90) {
            const increment = progress < 50 ? 5 : (progress < 80 ? 2 : 1)
            progress += increment
            setGenerationProgress(progress, `Generating ${actionType}...`)
        }
    }, 1000)
    try {
        const res = await fetchWithRetry(`${API_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record_id: currentRecordId, force })
        })
        const contentType = res.headers.get('content-type') || ''
        let data
        if (contentType.includes('application/json')) {
            data = await res.json()
        } else {
            const raw = await res.text()
            const short = raw.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 220)
            throw new Error(short || `Server returned ${res.status} without JSON.`)
        }
        if (!res.ok) throw new Error(data.error || 'Failed to generate')
        clearInterval(progressInterval)
        setGenerationProgress(100, 'Done!')
        await onSuccess(data.data)
        fetchUserStatus()
    } catch (e) {
        clearInterval(progressInterval)
        alert(e.message)
    } finally {
        stopGenerationOverlay()
    }
}

function renderTopics(markdown) {
    document.getElementById('topicsResult').innerHTML = marked.parse(markdown)
}

function renderQuiz(quizData) {
    let html = ''
    quizData.forEach((q, i) => {
        html += `
            <div class="quiz-question" id="q-${i}">
                <h3>${i + 1}. ${q.question}</h3>
                ${q.options.map((opt, optIdx) => `<div class="quiz-option" onclick="checkAnswer(${i}, ${optIdx}, ${q.correct_index})">${opt}</div>`).join('')}
                <div class="quiz-explanation" id="exp-${i}">${q.explanation}</div>
            </div>`
    })
    document.getElementById('quizResult').innerHTML = html
}

async function renderMindmap(mermaidText) {
    const container = document.getElementById('mindmapResult')
    try {
        let clean = mermaidText
        if (clean.includes('```mermaid')) {
            clean = clean.split('```mermaid')[1].split('```')[0].trim()
        } else if (clean.includes('```')) {
            clean = clean.replace(/```/g, '').trim()
        }
        container.innerHTML = `<div class="mermaid">${clean}</div>`

        const mindmapPane = document.getElementById('tab-mindmap')
        const wasHidden = mindmapPane && !mindmapPane.classList.contains('active')
        if (wasHidden) {
            mindmapPane.style.display = 'block'
            mindmapPane.style.position = 'absolute'
            mindmapPane.style.visibility = 'hidden'
        }
        try {
            await Promise.race([
                mermaid.run({ nodes: container.querySelectorAll('.mermaid') }),
                new Promise((_, reject) => setTimeout(() => reject(new Error('Mermaid render timeout')), 5000))
            ])
        } finally {
            if (wasHidden) {
                mindmapPane.style.display = ''
                mindmapPane.style.position = ''
                mindmapPane.style.visibility = ''
            }
        }
        const svg = container.querySelector('svg')
        if (svg && window.svgPanZoom) {
            svg.style.width = '100%'
            svg.style.height = '500px'
            svgPanZoom(svg, { controlIconsEnabled: true, zoomEnabled: true, panEnabled: true })
        }
    } catch (e) {
        console.error('Mermaid parsing error:', e)
        container.innerHTML = `<p style="color:var(--danger)">Failed to render mind map.</p><pre>${mermaidText}</pre>`
    }
}

document.getElementById('generateFlashcardsBtn').onclick = () => {
    const isRegen = document.getElementById('generateFlashcardsBtn').textContent.includes('Regenerate')
    callAI('/api/generate-flashcards', 'flashcards', (flashcards) => {
        currentFlashcards = flashcards
        renderFlashcards()
    }, isRegen)
}

document.getElementById('generateTopicsBtn').onclick = () => {
    const isRegen = document.getElementById('generateTopicsBtn').textContent.includes('Regenerate')
    callAI('/api/extract-topics', 'topics', (md) => renderTopics(md), isRegen)
}

document.getElementById('generateQuizBtn').onclick = () => {
    const isRegen = document.getElementById('generateQuizBtn').textContent.includes('Regenerate')
    callAI('/api/generate-quiz', 'quiz', (data) => renderQuiz(data), isRegen)
}

document.getElementById('generateMindmapBtn').onclick = () => {
    const isRegen = document.getElementById('generateMindmapBtn').textContent.includes('Regenerate')
    callAI('/api/generate-mindmap', 'mindmap', async (text) => await renderMindmap(text), isRegen)
}

let isGenerationActive = false

function setGenerationProgress(percent, msg) {
    if (!isGenerationActive) return
    const pBar = document.getElementById('generationProgressBar')
    const pText = document.getElementById('generationProgressText')
    const pMsg = document.getElementById('generationMessage')
    if (pBar) pBar.style.width = percent + '%'
    if (pText) pText.textContent = Math.floor(percent) + '%'
    if (msg && pMsg) {
        const current = pMsg.textContent
        if (current.includes('(Retrying')) {
            const retryText = current.match(/\(Retrying.*\)/)[0]
            pMsg.textContent = msg + ' ' + retryText
        } else {
            pMsg.textContent = msg
        }
    }
}

function startGenerationOverlay(initialMsg) {
    isGenerationActive = true
    document.getElementById('generationOverlay').style.display = 'flex'
    const pBar = document.getElementById('generationProgressBar')
    if (pBar) pBar.style.transition = 'width 0.3s ease-out'
    setGenerationProgress(0, initialMsg || 'Analyzing document...')
}

function stopGenerationOverlay() {
    if (!isGenerationActive) return
    setGenerationProgress(100, 'Finalizing...')
    setTimeout(() => {
        const overlay = document.getElementById('generationOverlay')
        if (overlay) overlay.style.display = 'none'
        isGenerationActive = false
    }, 500)
}
