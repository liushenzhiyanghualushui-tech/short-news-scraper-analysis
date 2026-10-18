# ---- 多阶段构建 ----
# 阶段1: Maven构建
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /build

# 配置阿里云 Maven 镜像
RUN mkdir -p /usr/share/maven/ref/conf && \
    echo '<?xml version="1.0" encoding="UTF-8"?>' > /usr/share/maven/ref/conf/settings.xml && \
    echo '<settings><mirrors><mirror><id>aliyun</id><name>Aliyun Maven</name><url>https://maven.aliyun.com/repository/public</url><mirrorOf>central</mirrorOf></mirror></mirrors></settings>' >> /usr/share/maven/ref/conf/settings.xml

# 复制源码
COPY pom.xml .
COPY src ./src

# 使用镜像构建
RUN mvn package -DskipTests -B -s /usr/share/maven/ref/conf/settings.xml -q

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
