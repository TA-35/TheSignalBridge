--
-- PostgreSQL database dump
--

\restrict W92I8QReJLNSeScuEpE7qjDCJvqoMqVQxOet2cWsXZRPnbxebRSpzVzT2cWersb

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO "user";

--
-- Name: credentials; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.credentials (
    id integer NOT NULL,
    user_id character varying(36) NOT NULL,
    credential_id bytea NOT NULL,
    public_key bytea NOT NULL,
    sign_count integer NOT NULL,
    transports character varying(120),
    created_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone
);


ALTER TABLE public.credentials OWNER TO "user";

--
-- Name: credentials_id_seq; Type: SEQUENCE; Schema: public; Owner: user
--

CREATE SEQUENCE public.credentials_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.credentials_id_seq OWNER TO "user";

--
-- Name: credentials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: user
--

ALTER SEQUENCE public.credentials_id_seq OWNED BY public.credentials.id;


--
-- Name: pairing_codes; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.pairing_codes (
    id integer NOT NULL,
    user_id character varying(36) NOT NULL,
    code_hash character varying(64) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone
);


ALTER TABLE public.pairing_codes OWNER TO "user";

--
-- Name: pairing_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: user
--

CREATE SEQUENCE public.pairing_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pairing_codes_id_seq OWNER TO "user";

--
-- Name: pairing_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: user
--

ALTER SEQUENCE public.pairing_codes_id_seq OWNED BY public.pairing_codes.id;


--
-- Name: patterns; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.patterns (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    category character varying(60) NOT NULL,
    implies text NOT NULL,
    why_misread text NOT NULL
);


ALTER TABLE public.patterns OWNER TO "user";

--
-- Name: patterns_id_seq; Type: SEQUENCE; Schema: public; Owner: user
--

CREATE SEQUENCE public.patterns_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.patterns_id_seq OWNER TO "user";

--
-- Name: patterns_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: user
--

ALTER SEQUENCE public.patterns_id_seq OWNED BY public.patterns.id;


--
-- Name: user_cards; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.user_cards (
    id integer NOT NULL,
    user_id character varying(36) NOT NULL,
    pattern_id character varying(40) NOT NULL,
    saved_at timestamp with time zone NOT NULL,
    last_opened_at timestamp with time zone
);


ALTER TABLE public.user_cards OWNER TO "user";

--
-- Name: user_cards_id_seq; Type: SEQUENCE; Schema: public; Owner: user
--

CREATE SEQUENCE public.user_cards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_cards_id_seq OWNER TO "user";

--
-- Name: user_cards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: user
--

ALTER SEQUENCE public.user_cards_id_seq OWNED BY public.user_cards.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.users (
    id character varying(36) NOT NULL,
    handle character varying(8) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL
);


ALTER TABLE public.users OWNER TO "user";

--
-- Name: credentials id; Type: DEFAULT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.credentials ALTER COLUMN id SET DEFAULT nextval('public.credentials_id_seq'::regclass);


--
-- Name: pairing_codes id; Type: DEFAULT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.pairing_codes ALTER COLUMN id SET DEFAULT nextval('public.pairing_codes_id_seq'::regclass);


--
-- Name: patterns id; Type: DEFAULT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.patterns ALTER COLUMN id SET DEFAULT nextval('public.patterns_id_seq'::regclass);


--
-- Name: user_cards id; Type: DEFAULT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.user_cards ALTER COLUMN id SET DEFAULT nextval('public.user_cards_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: credentials credentials_credential_id_key; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_credential_id_key UNIQUE (credential_id);


--
-- Name: credentials credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_pkey PRIMARY KEY (id);


--
-- Name: pairing_codes pairing_codes_code_hash_key; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.pairing_codes
    ADD CONSTRAINT pairing_codes_code_hash_key UNIQUE (code_hash);


--
-- Name: pairing_codes pairing_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.pairing_codes
    ADD CONSTRAINT pairing_codes_pkey PRIMARY KEY (id);


--
-- Name: patterns patterns_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.patterns
    ADD CONSTRAINT patterns_pkey PRIMARY KEY (id);


--
-- Name: user_cards uq_user_cards_user_pattern; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.user_cards
    ADD CONSTRAINT uq_user_cards_user_pattern UNIQUE (user_id, pattern_id);


--
-- Name: user_cards user_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.user_cards
    ADD CONSTRAINT user_cards_pkey PRIMARY KEY (id);


--
-- Name: users users_handle_key; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_handle_key UNIQUE (handle);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_credentials_user_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX ix_credentials_user_id ON public.credentials USING btree (user_id);


--
-- Name: ix_pairing_codes_code_hash; Type: INDEX; Schema: public; Owner: user
--

CREATE UNIQUE INDEX ix_pairing_codes_code_hash ON public.pairing_codes USING btree (code_hash);


--
-- Name: ix_pairing_codes_user_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX ix_pairing_codes_user_id ON public.pairing_codes USING btree (user_id);


--
-- Name: ix_user_cards_user_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX ix_user_cards_user_id ON public.user_cards USING btree (user_id);


--
-- Name: ix_users_handle; Type: INDEX; Schema: public; Owner: user
--

CREATE UNIQUE INDEX ix_users_handle ON public.users USING btree (handle);


--
-- Name: credentials credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.credentials
    ADD CONSTRAINT credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: pairing_codes pairing_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.pairing_codes
    ADD CONSTRAINT pairing_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_cards user_cards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.user_cards
    ADD CONSTRAINT user_cards_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict W92I8QReJLNSeScuEpE7qjDCJvqoMqVQxOet2cWsXZRPnbxebRSpzVzT2cWersb

