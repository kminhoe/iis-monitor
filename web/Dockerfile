FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 3000
# 데모 편의상 dev 모드. 실배포는 next build && next start.
CMD ["npm", "run", "dev"]
