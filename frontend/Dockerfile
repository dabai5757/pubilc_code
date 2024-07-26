FROM node:16-alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

EXPOSE ${FRONT_CONTAINER_PORT}

CMD ["npm", "start"]
