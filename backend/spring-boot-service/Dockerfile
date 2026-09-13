# ---- 多阶段构建 ----
# 阶段1: Maven构建
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /build
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

# 阶段2: 运行镜像
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

# 安装curl用于健康检查
RUN apk add --no-cache curl

# 复制构建产物
COPY --from=builder /build/target/*.jar app.jar

# Java 21 虚拟线程预览特性
ENV JAVA_OPTS="-Xms512m -Xmx1024m"

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
